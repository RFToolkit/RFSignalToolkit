#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from dataclasses import replace
from flask_cors import CORS,cross_origin
from flask import Flask, Response, request, render_template, send_from_directory
from flask.helpers import safe_join
from nbformat import write
import requests

from core.analyse import Analyse
from core.can import CAN
from core.udpAnalyser import UdPAnalyser
import matplotlib.pyplot as plt
from function.math1 import instanceSineWave
from function.dataframes import magnet, convertToMagnet
import struct
import json
import os
import numpy as np
import function.packetReader as packet
import os
import pandas as pd
import sys
import subprocess
from dotenv import load_dotenv
from core.Translator.DeeplAPI import Deepl
from deep_translator import GoogleTranslator
import gettext
import hexdump

# Load dotenv
load_dotenv()
TRACKER_URL=os.getenv('TRACKER_URL')
HOST=os.getenv('HOST')
PORT=os.getenv('PORT')

# SIGNAL FREQUENCY TYPE
signalRange={
  #'bluetooth': [.00001, .00002, .0001, 2400, 2483.5, 60000, 200000, 600000],
  #'wimax': [10000, 66000, 2000, 11000],
  #'lorawan': [433.05, 434.79, 863, 870, 902.3, 914.9],
  'wifi': [2.4 * (10**3), 5 * (10**3), 60 * (10**3)],
  #'manet': [300  * (10**3)],
  #'other': [9.20  * (10**3)]
}

wireless=[]
[ wireless.extend(x) for x in map(lambda x: signalRange.get(x), signalRange.keys()) ]

def extractor(dumplist):
    dumplist=[ *filter(lambda x: len(x.strip()) != 0, dumplist) ]
    MTU=1125# 1125 octet --> 9000 byte Jumbo ?
    count=int(len(dumplist)//MTU)
    count=count if count != 0 else 1
    print('searching..')
    try:
        text=''
        for i in range(int(len(dumplist) / count)):
            dump="".join(dumplist[i*count:(1+i)*count])
            sentence=''.join([ bytes.fromhex(dump[x:x+4]).decode('big5', 'replace').encode('iso-8859-15', 'replace').decode('utf-8', 'replace') for x in range(int(len(dump) / 4)) ])
            text+='\n' + sentence

        cutw=1000
        text=" ".join(text)
        print(text)
        print(hexdump.hexdump(text.encode('utf-8'), result='return'))
        exit(0)
        #import pycipher
        #for k in range(0,26):
        #    tr=pycipher.Caesar(k).decipher(text)
        #    print(tr if tr.__contains__('HK') and tr.__contains__('OR') and tr.__contains__('WHAT') else None)
        tmp=''
        for i in range(int(len(text) / cutw)):
            sentence=gettext.gettext(text[i*cutw:(i+1)*cutw:1])
            try:
                sentence = GoogleTranslator(source='auto', target='en').translate(sentence)
            except:
                sliceto=int(len(sentence)//8)
                for j in range(sliceto):
                    sentence = GoogleTranslator(source='auto', target='en').translate(sentence[j*sliceto:(j+1)*sliceto])
            sentence=Deepl().translate(str(sentence))
            tmp+=sentence
            print(tmp)

        sentence=hexdump.hexdump(tmp.encode('utf-8'), result='return')
        with open('./res', 'ab+') as res:
            res.write(bytes('{}\n*\n'.format(sentence).encode('utf-8')))
        res.close()
        packet=subprocess.run(["{}/packetExtractor/packet.sh".format(os.getcwd()) ], stdout=subprocess.PIPE)
        if packet.returncode == 0:
            if len(packet.stdout):
                print(packet.stdout)
                yield bytes(str(packet.stdout).encode('utf-8'))
                
    finally:
        print("End")

def iptrack():
    data=""
    try:
        data=subprocess.run(["{}/packetExtractor/ips.sh".format(os.getcwd()), "{}/packetExtractor/set".format(os.getcwd())], stdout=subprocess.PIPE)
        if data.returncode == 0:
            for ip in [*filter(lambda x: len(x)>0, data.stdout.decode("utf-8").split('\n'))]:
                response=requests.get(TRACKER_URL + '/list/{}'.format(ip))
                yield bytes(response.text.encode('utf-8'))
    finally:
        print("End")        

app = Flask(__name__)
static = safe_join(os.path.dirname(__file__), 'views')
CORS_ALLOW_ORIGIN="*,*"
CORS_EXPOSE_HEADERS="*,*"
CORS_ALLOW_HEADERS="content-type,origin,*"
cors = CORS(
    app, origins=CORS_ALLOW_ORIGIN.split(","), 
    allow_headers=CORS_ALLOW_HEADERS.split(","),
    expose_headers= CORS_EXPOSE_HEADERS.split(","),
    resources={r"/*": {"origins": "*"}},
    supports_credentials = True
)

@app.route('/data', methods=['GET'])
@cross_origin(supports_credentials=True)
def views():
    return send_from_directory(static, 'index.html')
    
@app.route('/data/text', methods=['GET'])
def translatedtext():
    return """<h1>Hello, World!</h1>"""

@app.route('/data/json', methods=['GET'])
@cross_origin(supports_credentials=True)
def jsondata():
    return Response(iptrack(), mimetype="application/json", headers={
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Origin, X-Requested-With, Content-Type, Authorization, Accept',
    })

@app.route('/dynmagnet', methods=['POST', 'GET'])
def dyns():
    analyse = Analyse()
    signal = None
    dumpShiftedLeft=[]
    i = 2400
    df=convertToMagnet(request.get_json())
    sig=[]

    # Search from frequency range 1000000000 hertz to 900000000000 hertz
    for FREQUENCY in wireless:
        print('[APP]: is running for {} Mhz'.format(FREQUENCY))
        #for j in range(1):
        #analyse.provideDataset(False, df[j:]) if len(df[j:]) < MTU else analyse.provideDataset(False, df[j:j+MTU])
        analyse.provideDataset(False, df)
        signal = analyse.changeFrequency( FREQUENCY )
        if signal:
            numericalAnalysis=CAN()
            s=numericalAnalysis.qbits(numericalAnalysis.can(15, signal[1].real))
            if(s not in sig):
                p=''.join(s)
                sig.append(p)
                dumpShiftedLeft+=[p] +[ ''.join([ hex(int(p[x:x+2], 16) ^ i)[2:] for x in range(int(len(p) / 2)) ]) for i in range(127) ]

    return Response(extractor(dumpShiftedLeft), mimetype="application/json")
                    

    #else:
    #    return json.dumps({ "state": "null" })

@app.route('/magnet', methods=['POST'])
def push():
    #analyse = Analyse()
    #udp=UdPAnalyser()
    #analyse.provideDataset(os.getcwd() +'/json/radio.csv')
    #signal = analyse.changeFrequency(30)
    #s=''
    #if signal:
    #    numericalAnalysis=CAN()
    #    signal=[numericalAnalysis.can(16, signal[1].real), numericalAnalysis.can(16, signal[1].imag)]
    #    s=numericalAnalysis.qbits(signal[0])

    return json.dumps({
        'magnet': [magnet(req, mode = 'w' if i == 0 else 'a', filename='./radio.csv') for i, req in enumerate(request.get_json())],
    })

if __name__ == "__main__":
    app.run(debug=True, use_reloader=True, host=HOST, port=PORT)