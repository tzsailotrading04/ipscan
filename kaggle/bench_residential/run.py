# bench-residential-throughput-v3
# Stage-by-Stage Non-CDN Raw Throughput & Diagnosis Benchmark
import asyncio
import socket
import ssl
import time
import json
import sys
import os

SAMPLE_PROXIES = [{'proxy': '50.75.16.123:80', 'asn': '11351', 'cc': 'US', 'org': 'TWC-11351-NORTHEAST', 'is_us_eu': True, 'group': 'global_residential'}, {'proxy': '107.155.198.51:443', 'asn': '19194', 'cc': 'US', 'org': 'JOVITA', 'is_us_eu': True, 'group': 'global_residential'}, {'proxy': '45.124.171.189:8090', 'asn': '9441', 'cc': 'BD', 'org': 'NEXT-BD Next Online Limited.', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '188.116.133.4:3128', 'asn': '34629', 'cc': 'RU', 'org': 'ORNRU-AS Kvant-telecom uplink:', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '132.148.114.177:80', 'asn': '398101', 'cc': 'US', 'org': 'GO-DADDY-COM-LLC', 'is_us_eu': True, 'group': 'global_residential'}, {'proxy': '23.226.69.44:443', 'asn': '53755', 'cc': 'US', 'org': 'IOFLOOD', 'is_us_eu': True, 'group': 'global_residential'}, {'proxy': '5.56.29.119:80', 'asn': '219048', 'cc': 'IN', 'org': 'SUN-IT-SOLUTIONS - Sachin Kothawade trading as SUN IT SOLUTIONS', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '202.91.227.170:80', 'asn': '4837', 'cc': 'CN', 'org': 'CHINA169-BACKBONE CHINA UNICOM China169 Backbone', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '74.204.221.143:80', 'asn': '17088', 'cc': 'US', 'org': 'CURRENEX', 'is_us_eu': True, 'group': 'global_residential'}, {'proxy': '27.126.246.21:80', 'asn': '45474', 'cc': 'SG', 'org': 'NEXUSGUARD-AS-AP NEXUSGUARD LIMITED', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '60.43.200.176:80', 'asn': '4713', 'cc': 'JP', 'org': 'OCN NTT Communications Corporation', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '18.9.107.11:80', 'asn': '3', 'cc': 'US', 'org': 'MIT-GATEWAYS', 'is_us_eu': True, 'group': 'global_residential'}, {'proxy': '38.11.224.138:443', 'asn': '398478', 'cc': 'US', 'org': 'PEG-HK', 'is_us_eu': True, 'group': 'global_residential'}, {'proxy': '38.78.242.29:80', 'asn': '36223', 'cc': 'US', 'org': 'SPANISHFORK-COMMUNITY-NETWORK', 'is_us_eu': True, 'group': 'global_residential'}, {'proxy': '27.126.240.139:80', 'asn': '45474', 'cc': 'SG', 'org': 'NEXUSGUARD-AS-AP NEXUSGUARD LIMITED', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '38.173.21.121:443', 'asn': '398478', 'cc': 'US', 'org': 'PEG-HK', 'is_us_eu': True, 'group': 'global_residential'}, {'proxy': '38.38.231.171:443', 'asn': '394432', 'cc': 'US', 'org': 'PEG-SG', 'is_us_eu': True, 'group': 'global_residential'}, {'proxy': '71.6.6.186:80', 'asn': '14265', 'cc': 'US', 'org': 'US-TELEPACIFIC', 'is_us_eu': True, 'group': 'global_residential'}, {'proxy': '27.126.217.198:80', 'asn': '45474', 'cc': 'SG', 'org': 'NEXUSGUARD-AS-AP NEXUSGUARD LIMITED', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '23.248.231.3:443', 'asn': '138415', 'cc': 'HK', 'org': 'YANCYLIMITED-AS-HK Yancy Limited', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '51.159.199.100:80', 'asn': '12876', 'cc': 'FR', 'org': 'Online SAS', 'is_us_eu': True, 'group': 'global_residential'}, {'proxy': '39.1.84.221:80', 'asn': '18182', 'cc': 'TW', 'org': 'SONET-TW Sony Network Taiwan Limited', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '106.250.161.106:80', 'asn': '3786', 'cc': 'KR', 'org': 'LGDACOM LG DACOM Corporation', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '222.122.49.23:80', 'asn': '4766', 'cc': 'KR', 'org': 'KIXS-AS-KR Korea Telecom', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '192.132.141.59:80', 'asn': '6079', 'cc': 'US', 'org': 'RCN-AS', 'is_us_eu': True, 'group': 'global_residential'}, {'proxy': '60.12.226.111:443', 'asn': '4837', 'cc': 'CN', 'org': 'CHINA169-BACKBONE CHINA UNICOM China169 Backbone', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '27.126.216.66:80', 'asn': '45474', 'cc': 'SG', 'org': 'NEXUSGUARD-AS-AP NEXUSGUARD LIMITED', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '62.146.133.147:80', 'asn': '15598', 'cc': 'DE', 'org': 'IPX-AS15598', 'is_us_eu': True, 'group': 'global_residential'}, {'proxy': '24.234.57.229:80', 'asn': '22773', 'cc': 'US', 'org': 'ASN-CXA-ALL-CCI-22773-RDC', 'is_us_eu': True, 'group': 'global_residential'}, {'proxy': '41.93.32.54:80', 'asn': '37182', 'cc': 'TZ', 'org': 'TERNET', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '61.13.134.6:80', 'asn': '134078', 'cc': 'SG', 'org': 'NETPLUZ-AS-AP NETPLUZ HOLDINGS PRIVATE LIMITED', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '103.10.203.248:80', 'asn': '45559', 'cc': 'PH', 'org': 'QUZATECH-PH MCPO Box 1755', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '37.252.191.32:443', 'asn': '44133', 'cc': 'AT', 'org': 'IPAX-AS', 'is_us_eu': True, 'group': 'global_residential'}, {'proxy': '27.126.216.118:80', 'asn': '45474', 'cc': 'SG', 'org': 'NEXUSGUARD-AS-AP NEXUSGUARD LIMITED', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '78.142.229.166:80', 'asn': '3214', 'cc': 'DE', 'org': 'XTOM xTom GmbH', 'is_us_eu': True, 'group': 'global_residential'}, {'proxy': '50.63.131.241:80', 'asn': '398101', 'cc': 'US', 'org': 'GO-DADDY-COM-LLC', 'is_us_eu': True, 'group': 'global_residential'}, {'proxy': '72.194.40.16:80', 'asn': '22773', 'cc': 'US', 'org': 'ASN-CXA-ALL-CCI-22773-RDC', 'is_us_eu': True, 'group': 'global_residential'}, {'proxy': '62.146.117.54:80', 'asn': '15598', 'cc': 'DE', 'org': 'IPX-AS15598', 'is_us_eu': True, 'group': 'global_residential'}, {'proxy': '91.24.105.164:443', 'asn': '3320', 'cc': 'DE', 'org': 'DTAG Internet service provider operations', 'is_us_eu': True, 'group': 'global_residential'}, {'proxy': '62.182.194.103:80', 'asn': '42532', 'cc': 'LV', 'org': 'VEESP-LV-AS', 'is_us_eu': True, 'group': 'global_residential'}, {'proxy': '27.126.202.51:80', 'asn': '45474', 'cc': 'SG', 'org': 'NEXUSGUARD-AS-AP NEXUSGUARD LIMITED', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '27.126.239.241:80', 'asn': '45474', 'cc': 'SG', 'org': 'NEXUSGUARD-AS-AP NEXUSGUARD LIMITED', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '71.75.44.3:80', 'asn': '11426', 'cc': 'US', 'org': 'TWC-11426-CAROLINAS', 'is_us_eu': True, 'group': 'global_residential'}, {'proxy': '68.178.163.151:443', 'asn': '26496', 'cc': 'US', 'org': 'AS-26496-GO-DADDY-COM-LLC', 'is_us_eu': True, 'group': 'global_residential'}, {'proxy': '157.254.20.12:10808', 'asn': '202662', 'cc': 'HK', 'org': 'Hytron Network', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '43.248.2.114:80', 'asn': '146817', 'cc': 'CN', 'org': 'FXNET Hubei Feixun Network Co., Ltd', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '14.45.139.153:80', 'asn': '4766', 'cc': 'KR', 'org': 'KIXS-AS-KR Korea Telecom', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '45.116.42.34:80', 'asn': '45474', 'cc': 'SG', 'org': 'NEXUSGUARD-AS-AP NEXUSGUARD LIMITED', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '31.56.188.7:80', 'asn': '213915', 'cc': 'GB', 'org': 'PHILIPP-MORIS-TRETTIN', 'is_us_eu': True, 'group': 'global_residential'}, {'proxy': '45.116.43.186:80', 'asn': '45474', 'cc': 'SG', 'org': 'NEXUSGUARD-AS-AP NEXUSGUARD LIMITED', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '38.6.80.235:80', 'asn': '398823', 'cc': 'US', 'org': 'PEG-LA', 'is_us_eu': True, 'group': 'global_residential'}, {'proxy': '27.126.250.23:80', 'asn': '45474', 'cc': 'SG', 'org': 'NEXUSGUARD-AS-AP NEXUSGUARD LIMITED', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '67.21.68.132:80', 'asn': '46844', 'cc': 'US', 'org': 'SHARKTECH', 'is_us_eu': True, 'group': 'global_residential'}, {'proxy': '38.39.208.195:80', 'asn': '55140', 'cc': 'US', 'org': 'SHO-ME-TECHNOLOGIES', 'is_us_eu': True, 'group': 'global_residential'}, {'proxy': '62.138.147.173:80', 'asn': '8972', 'cc': 'DE', 'org': 'GD-EMEA-DC-SXB1', 'is_us_eu': True, 'group': 'global_residential'}, {'proxy': '50.115.18.100:443', 'asn': '53861', 'cc': 'US', 'org': 'AS-KGIX', 'is_us_eu': True, 'group': 'global_residential'}, {'proxy': '38.174.152.180:80', 'asn': '399195', 'cc': 'US', 'org': 'PEG-KR', 'is_us_eu': True, 'group': 'global_residential'}, {'proxy': '24.179.246.80:80', 'asn': '20115', 'cc': 'US', 'org': 'CHARTER-20115', 'is_us_eu': True, 'group': 'global_residential'}, {'proxy': '45.163.116.88:443', 'asn': '268577', 'cc': 'BR', 'org': 'LIGEIRO FIBRA TELECOM LTDA', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '38.173.248.150:443', 'asn': '398478', 'cc': 'US', 'org': 'PEG-HK', 'is_us_eu': True, 'group': 'global_residential'}, {'proxy': '60.250.218.83:443', 'asn': '3462', 'cc': 'TW', 'org': 'HINET Data Communication Business Group', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '49.247.13.42:443', 'asn': '38700', 'cc': 'KR', 'org': 'SMILESERV-AS-KR SMILESERV', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '81.19.128.206:443', 'asn': '24658', 'cc': 'RU', 'org': 'IVC-AS', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '188.95.252.36:80', 'asn': '197518', 'cc': 'ES', 'org': 'RACKMARKT', 'is_us_eu': True, 'group': 'global_residential'}, {'proxy': '43.254.49.12:80', 'asn': '45117', 'cc': 'IN', 'org': 'INPL-IN-AP Ishans Network', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '64.7.68.102:80', 'asn': '53497', 'cc': 'US', 'org': 'WEBPERCEPTION', 'is_us_eu': True, 'group': 'global_residential'}, {'proxy': '45.141.148.122:80', 'asn': '44382', 'cc': 'US', 'org': 'WHITELABEL', 'is_us_eu': True, 'group': 'global_residential'}, {'proxy': '50.122.109.182:80', 'asn': '5650', 'cc': 'US', 'org': 'FRONTIER-FRTR', 'is_us_eu': True, 'group': 'global_residential'}, {'proxy': '38.11.224.135:443', 'asn': '398478', 'cc': 'US', 'org': 'PEG-HK', 'is_us_eu': True, 'group': 'global_residential'}, {'proxy': '27.126.240.14:80', 'asn': '45474', 'cc': 'SG', 'org': 'NEXUSGUARD-AS-AP NEXUSGUARD LIMITED', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '45.41.205.96:80', 'asn': '32181', 'cc': 'US', 'org': 'ASN-GIGENET', 'is_us_eu': True, 'group': 'global_residential'}, {'proxy': '38.14.176.163:80', 'asn': '54600', 'cc': 'US', 'org': 'PEG-SV', 'is_us_eu': True, 'group': 'global_residential'}, {'proxy': '45.123.160.123:80', 'asn': '58765', 'cc': 'IN', 'org': 'BTEL-AS-IN B TEL INTERNET PRIVATE LIMITED', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '47.19.18.30:443', 'asn': '54004', 'cc': 'US', 'org': 'OPTIMUM-WIFI2', 'is_us_eu': True, 'group': 'global_residential'}, {'proxy': '38.65.81.240:80', 'asn': '398946', 'cc': 'US', 'org': 'CONTENTKEEPER-AS-ARIN', 'is_us_eu': True, 'group': 'global_residential'}, {'proxy': '14.139.211.196:80', 'asn': '55824', 'cc': 'IN', 'org': 'NKN-CORE-NW NKN Core Network', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '38.60.179.57:443', 'asn': '154177', 'cc': 'HK', 'org': 'LIGHT4-AS-AP LIGHT NODE LIMITED', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '103.3.244.111:443', 'asn': '135967', 'cc': 'VN', 'org': 'BKNS-AS-VN Bach Kim Network solutions Join stock company', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '31.210.61.15:80', 'asn': '42910', 'cc': 'TR', 'org': 'PREMIERDC-VERI-MERKEZI-ANONIM-SIRKETI PREMIERDC', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '64.81.235.239:80', 'asn': '6079', 'cc': 'US', 'org': 'RCN-AS', 'is_us_eu': True, 'group': 'global_residential'}, {'proxy': '49.247.33.71:80', 'asn': '38700', 'cc': 'KR', 'org': 'SMILESERV-AS-KR SMILESERV', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '23.231.76.76:80', 'asn': '62904', 'cc': 'US', 'org': 'AS62904 - Eonix Corporation', 'is_us_eu': True, 'group': 'global_residential'}, {'proxy': '45.167.204.87:80', 'asn': '267993', 'cc': 'BR', 'org': 'ALPHA FIBRA SERVICOS DE COMUNICACAO MULTIMIDIA SCM', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '59.120.94.241:80', 'asn': '3462', 'cc': 'TW', 'org': 'HINET Data Communication Business Group', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '42.96.50.26:80', 'asn': '45903', 'cc': 'VN', 'org': 'CMCTELECOM-VN CMC Telecom Infrastructure Company', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '103.22.157.13:80', 'asn': '45504', 'cc': 'PH', 'org': 'SPLUNKNET-PH MCPO Box 1906', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '45.7.230.194:443', 'asn': '52368', 'cc': 'CL', 'org': 'ZAM LTDA.', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '69.124.90.79:80', 'asn': '6128', 'cc': 'US', 'org': 'CABLE-NET-1', 'is_us_eu': True, 'group': 'global_residential'}, {'proxy': '45.116.41.53:80', 'asn': '45474', 'cc': 'SG', 'org': 'NEXUSGUARD-AS-AP NEXUSGUARD LIMITED', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '27.126.206.2:80', 'asn': '45474', 'cc': 'SG', 'org': 'NEXUSGUARD-AS-AP NEXUSGUARD LIMITED', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '41.111.172.6:443', 'asn': '36947', 'cc': 'DZ', 'org': 'ALGTEL-AS', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '59.16.156.181:80', 'asn': '4766', 'cc': 'KR', 'org': 'KIXS-AS-KR Korea Telecom', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '23.235.170.90:443', 'asn': '138415', 'cc': 'HK', 'org': 'YANCYLIMITED-AS-HK Yancy Limited', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '45.116.40.129:80', 'asn': '45474', 'cc': 'SG', 'org': 'NEXUSGUARD-AS-AP NEXUSGUARD LIMITED', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '38.33.178.224:443', 'asn': '398478', 'cc': 'US', 'org': 'PEG-HK', 'is_us_eu': True, 'group': 'global_residential'}, {'proxy': '51.158.170.128:443', 'asn': '12876', 'cc': 'FR', 'org': 'Online SAS', 'is_us_eu': True, 'group': 'global_residential'}, {'proxy': '49.175.178.45:80', 'asn': '17858', 'cc': 'KR', 'org': 'POWERVIS-AS-KR LG POWERCOMM', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '45.74.31.46:10982', 'asn': '219326', 'cc': 'GB', 'org': 'SULAVIL - SULAVI LTD', 'is_us_eu': True, 'group': 'global_residential'}, {'proxy': '198.15.30.70:8080', 'asn': '154503', 'cc': 'ID', 'org': 'IDNIC-TRIMAFA-AS-ID PT Trimafa Computindo Networking', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '31.76.253.179:80', 'asn': '43260', 'cc': 'TR', 'org': 'AS43260 - DGN TEKNOLOJI A.S.', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '38.183.146.33:8080', 'asn': '140457', 'cc': 'ID', 'org': 'IMEDIANET-AS-ID PT Ikhlas Cipta Teknologi', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '60.248.168.58:80', 'asn': '3462', 'cc': 'TW', 'org': 'HINET Data Communication Business Group', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '156.234.241.239:443', 'asn': '138415', 'cc': 'HK', 'org': 'YANCYLIMITED-AS-HK Yancy Limited', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '69.30.204.93:80', 'asn': '32097', 'cc': 'US', 'org': 'WII', 'is_us_eu': True, 'group': 'global_residential'}, {'proxy': '45.145.56.123:80', 'asn': '198883', 'cc': 'BG', 'org': 'asd-as - Tabunscic Anatoli', 'is_us_eu': True, 'group': 'global_residential'}, {'proxy': '185.244.174.230:80', 'asn': '215997', 'cc': 'RU', 'org': 'AQ-AS', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '45.227.186.146:80', 'asn': '267033', 'cc': 'BR', 'org': 'serrasul telecom ltda', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '46.205.224.136:80', 'asn': '12912', 'cc': 'PL', 'org': 'TM', 'is_us_eu': True, 'group': 'global_residential'}, {'proxy': '27.126.211.177:80', 'asn': '45474', 'cc': 'SG', 'org': 'NEXUSGUARD-AS-AP NEXUSGUARD LIMITED', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '23.227.197.162:443', 'asn': '29802', 'cc': 'US', 'org': 'HVC-AS', 'is_us_eu': True, 'group': 'global_residential'}, {'proxy': '24.103.153.73:80', 'asn': '11351', 'cc': 'US', 'org': 'TWC-11351-NORTHEAST', 'is_us_eu': True, 'group': 'global_residential'}, {'proxy': '41.93.32.129:80', 'asn': '37182', 'cc': 'TZ', 'org': 'TERNET', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '195.174.100.174:1080', 'asn': '9121', 'cc': 'TR', 'org': 'TTNET', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '60.199.235.135:80', 'asn': '9924', 'cc': 'TW', 'org': 'TFN-TW Taiwan Fixed Network, Telco and Network Service Provider.', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '58.4.45.209:80', 'asn': '17506', 'cc': 'JP', 'org': 'UCOM ARTERIA Networks Corporation', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '43.242.194.245:80', 'asn': '146817', 'cc': 'CN', 'org': 'FXNET Hubei Feixun Network Co., Ltd', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '217.175.46.2:1080', 'asn': '38917', 'cc': 'RU', 'org': 'KOMTEL-AS', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '62.182.51.58:443', 'asn': '44678', 'cc': 'RU', 'org': 'TVT-NET', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '160.19.41.50:80', 'asn': '142461', 'cc': 'IN', 'org': 'ATCINFO-AS-IN ATC INFOCOM SOLUTIONS PVT LTD', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '61.220.205.148:80', 'asn': '3462', 'cc': 'TW', 'org': 'HINET Data Communication Business Group', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '70.175.229.42:80', 'asn': '22773', 'cc': 'US', 'org': 'ASN-CXA-ALL-CCI-22773-RDC', 'is_us_eu': True, 'group': 'global_residential'}, {'proxy': '50.123.111.241:80', 'asn': '20055', 'cc': 'US', 'org': 'AS-WHOLESAIL', 'is_us_eu': True, 'group': 'global_residential'}, {'proxy': '27.126.249.109:80', 'asn': '45474', 'cc': 'SG', 'org': 'NEXUSGUARD-AS-AP NEXUSGUARD LIMITED', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '38.194.49.243:80', 'asn': '18615', 'cc': 'US', 'org': 'MAINSTREAM-FIBER', 'is_us_eu': True, 'group': 'global_residential'}, {'proxy': '58.136.124.104:80', 'asn': '133481', 'cc': 'TH', 'org': 'AIS-FIBRE-AS-AP AIS Fibre', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '31.99.202.188:443', 'asn': '21859', 'cc': 'US', 'org': 'ZEN-ECN', 'is_us_eu': True, 'group': 'global_residential'}, {'proxy': '45.177.152.19:80', 'asn': '268985', 'cc': 'BR', 'org': 'VEM PRA UNO PROVEDOR DE INTERNET LTDA', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '210.99.209.155:80', 'asn': '4766', 'cc': 'KR', 'org': 'KIXS-AS-KR Korea Telecom', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '171.245.71.144:1080', 'asn': '7552', 'cc': 'VN', 'org': 'VIETEL-AS-AP Viettel Group', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '27.126.212.135:80', 'asn': '45474', 'cc': 'SG', 'org': 'NEXUSGUARD-AS-AP NEXUSGUARD LIMITED', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '68.178.151.121:80', 'asn': '26496', 'cc': 'US', 'org': 'AS-26496-GO-DADDY-COM-LLC', 'is_us_eu': True, 'group': 'global_residential'}, {'proxy': '42.61.61.221:80', 'asn': '3758', 'cc': 'SG', 'org': 'SINGNET SingNet', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '23.229.237.103:80', 'asn': '398101', 'cc': 'US', 'org': 'GO-DADDY-COM-LLC', 'is_us_eu': True, 'group': 'global_residential'}, {'proxy': '210.94.22.52:80', 'asn': '9318', 'cc': 'KR', 'org': 'SKB-AS SK Broadband Co Ltd', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '51.159.78.184:80', 'asn': '12876', 'cc': 'FR', 'org': 'Online SAS', 'is_us_eu': True, 'group': 'global_residential'}, {'proxy': '49.247.44.20:80', 'asn': '38700', 'cc': 'KR', 'org': 'SMILESERV-AS-KR SMILESERV', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '27.105.209.41:80', 'asn': '18182', 'cc': 'TW', 'org': 'SONET-TW Sony Network Taiwan Limited', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '45.43.92.57:443', 'asn': '213535', 'cc': 'SA', 'org': 'YOTTASRC', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '103.147.92.60:80', 'asn': '139959', 'cc': 'ID', 'org': 'IDNIC-UPNVJ-AS-ID Universitas Pembangunan Nasional Veteran Jakarta', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '69.197.139.226:80', 'asn': '32097', 'cc': 'US', 'org': 'WII', 'is_us_eu': True, 'group': 'global_residential'}, {'proxy': '60.212.190.87:80', 'asn': '4837', 'cc': 'CN', 'org': 'CHINA169-BACKBONE CHINA UNICOM China169 Backbone', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '31.77.241.168:80', 'asn': '216129', 'cc': 'PL', 'org': 'GUARDNETWORK-AS', 'is_us_eu': True, 'group': 'global_residential'}, {'proxy': '42.62.176.229:80', 'asn': '55690', 'cc': 'ID', 'org': 'ANDIRA-AS-ID PT Andira Infomedia', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '46.158.140.232:80', 'asn': '12389', 'cc': 'RU', 'org': 'ROSTELECOM-AS PJSC Rostelecom. Technical Team', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '38.14.176.154:80', 'asn': '54600', 'cc': 'US', 'org': 'PEG-SV', 'is_us_eu': True, 'group': 'global_residential'}, {'proxy': '27.254.153.246:80', 'asn': '63940', 'cc': 'TH', 'org': 'DRAGONHISPEED-AS-AP dragonhispeed', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '43.254.49.173:80', 'asn': '45117', 'cc': 'IN', 'org': 'INPL-IN-AP Ishans Network', 'is_us_eu': False, 'group': 'global_residential'}, {'proxy': '31.58.240.166:80', 'asn': '213915', 'cc': 'GB', 'org': 'PHILIPP-MORIS-TRETTIN', 'is_us_eu': True, 'group': 'global_residential'}, {'proxy': '80.119.144.237:80', 'asn': '15557', 'cc': 'FR', 'org': 'LDCOMNET --- I3Dnet ---', 'is_us_eu': True, 'group': 'global_residential'}, {'proxy': '62.149.192.130:80', 'asn': '31034', 'cc': 'IT', 'org': 'ARUBA-ASN', 'is_us_eu': True, 'group': 'global_residential'}, {'proxy': '66.206.15.50:443', 'asn': '29802', 'cc': 'US', 'org': 'HVC-AS', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '51.15.122.124:80', 'asn': '12876', 'cc': 'FR', 'org': 'Online SAS', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '46.183.100.208:80', 'asn': '34953', 'cc': 'DE', 'org': 'RELAIX RelAix Networks GmbH', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '45.147.48.40:80', 'asn': '3214', 'cc': 'DE', 'org': 'XTOM xTom GmbH', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '69.5.175.56:80', 'asn': '25369', 'cc': 'GB', 'org': 'BANDWIDTH-AS', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '38.58.182.178:80', 'asn': '26042', 'cc': 'US', 'org': 'FIBERSTATE', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '69.5.175.78:80', 'asn': '25369', 'cc': 'GB', 'org': 'BANDWIDTH-AS', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '46.21.233.83:80', 'asn': '34762', 'cc': 'BE', 'org': 'COMBELL-AS', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '66.206.6.60:80', 'asn': '29802', 'cc': 'US', 'org': 'HVC-AS', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '45.93.196.53:80', 'asn': '35042', 'cc': 'DE', 'org': 'LAYER7-NETWORKS-', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '65.35.201.147:80', 'asn': '33363', 'cc': 'US', 'org': 'BHN-33363', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '217.91.192.181:80', 'asn': '3320', 'cc': 'DE', 'org': 'DTAG Internet service provider operations', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '38.38.243.144:443', 'asn': '398478', 'cc': 'US', 'org': 'PEG-HK', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '66.154.79.48:80', 'asn': '22653', 'cc': 'US', 'org': 'GLOBALCOMPASS', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '63.141.236.251:80', 'asn': '33387', 'cc': 'US', 'org': 'NOCIX', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '64.22.68.15:80', 'asn': '13767', 'cc': 'US', 'org': 'DATABANK-DFW', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '66.112.153.132:80', 'asn': '8119', 'cc': 'US', 'org': 'DTN-AS', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '128.195.247.20:80', 'asn': '299', 'cc': 'US', 'org': 'UCINET-AS', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '185.158.64.3:80', 'asn': '202657', 'cc': 'CZ', 'org': 'HNOJNIK', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '70.182.90.112:80', 'asn': '22773', 'cc': 'US', 'org': 'ASN-CXA-ALL-CCI-22773-RDC', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '46.144.27.165:80', 'asn': '1136', 'cc': 'NL', 'org': 'KPN KPN National', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '45.74.31.41:12849', 'asn': '219326', 'cc': 'GB', 'org': 'SULAVIL - SULAVI LTD', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '51.158.163.43:80', 'asn': '12876', 'cc': 'FR', 'org': 'Online SAS', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '69.61.120.82:80', 'asn': '22653', 'cc': 'US', 'org': 'GLOBALCOMPASS', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '31.182.46.114:80', 'asn': '16342', 'cc': 'PL', 'org': 'TOYA TOYA Sp. z o.o.', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '68.115.219.155:80', 'asn': '20115', 'cc': 'US', 'org': 'CHARTER-20115', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '64.81.239.87:80', 'asn': '6079', 'cc': 'US', 'org': 'RCN-AS', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '38.175.116.128:80', 'asn': '35487', 'cc': 'US', 'org': 'MISAKA', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '67.61.143.138:80', 'asn': '11492', 'cc': 'US', 'org': 'CABLEONE', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '46.228.205.227:443', 'asn': '24961', 'cc': 'DE', 'org': 'MYLOC-AS IP Backbone of WIIT AG formerly myLoc managed IT AG', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '45.91.251.197:80', 'asn': '44486', 'cc': 'DE', 'org': 'SYNLINQ synlinq.de', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '64.184.186.151:80', 'asn': '16713', 'cc': 'US', 'org': 'NOANET-WA', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '192.132.191.204:80', 'asn': '6079', 'cc': 'US', 'org': 'RCN-AS', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '38.38.133.39:80', 'asn': '54600', 'cc': 'US', 'org': 'PEG-SV', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '24.182.202.27:80', 'asn': '20115', 'cc': 'US', 'org': 'CHARTER-20115', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '38.12.64.137:80', 'asn': '54600', 'cc': 'US', 'org': 'PEG-SV', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '199.80.53.241:80', 'asn': '40824', 'cc': 'US', 'org': 'WZ-US-40824', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '63.141.236.130:80', 'asn': '33387', 'cc': 'US', 'org': 'NOCIX', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '45.74.31.41:9293', 'asn': '219326', 'cc': 'GB', 'org': 'SULAVIL - SULAVI LTD', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '5.231.31.6:80', 'asn': '213850', 'cc': 'DE', 'org': 'NEXOSYSTEMS', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '62.28.144.184:443', 'asn': '15525', 'cc': 'PT', 'org': 'MEO-EMPRESAS', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '64.22.89.111:80', 'asn': '6079', 'cc': 'US', 'org': 'RCN-AS', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '45.74.31.46:4259', 'asn': '219326', 'cc': 'GB', 'org': 'SULAVIL - SULAVI LTD', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '90.90.35.224:80', 'asn': '3215', 'cc': 'FR', 'org': 'France Telecom - Orange', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '64.51.5.46:80', 'asn': '7459', 'cc': 'US', 'org': 'GRANDECOM-AS1', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '45.152.70.2:80', 'asn': '211615', 'cc': 'FR', 'org': 'NETARIS', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '38.127.37.215:443', 'asn': '18978', 'cc': 'US', 'org': 'ENZUINC-', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '79.153.249.59:80', 'asn': '3352', 'cc': 'ES', 'org': 'TELEFONICA_DE_ESPANA', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '207.192.177.50:80', 'asn': '63005', 'cc': 'US', 'org': 'NEXUS-22-63005', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '38.14.176.176:80', 'asn': '54600', 'cc': 'US', 'org': 'PEG-SV', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '45.144.172.161:80', 'asn': '26383', 'cc': 'US', 'org': 'ASNET', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '207.192.140.231:80', 'asn': '63005', 'cc': 'US', 'org': 'NEXUS-22-63005', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '64.237.26.1:80', 'asn': '30036', 'cc': 'US', 'org': 'MEDIACOM-ENTERPRISE-BUSINESS', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '31.58.240.115:80', 'asn': '213915', 'cc': 'GB', 'org': 'PHILIPP-MORIS-TRETTIN', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '68.178.224.202:80', 'asn': '26496', 'cc': 'US', 'org': 'AS-26496-GO-DADDY-COM-LLC', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '184.178.172.11:4145', 'asn': '22773', 'cc': 'US', 'org': 'ASN-CXA-ALL-CCI-22773-RDC', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '50.2.64.36:80', 'asn': '62904', 'cc': 'US', 'org': 'AS62904 - Eonix Corporation', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '94.249.150.91:1080', 'asn': '209874', 'cc': 'PT', 'org': 'TECHTIDE', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '38.178.243.135:80', 'asn': '35986', 'cc': 'US', 'org': 'VYVE-BROADBAND', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '31.56.185.114:80', 'asn': '219064', 'cc': 'GB', 'org': 'Akenai-Products-AS - Akenai Products LTD', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '64.81.229.70:80', 'asn': '6079', 'cc': 'US', 'org': 'RCN-AS', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '74.2.131.65:80', 'asn': '6079', 'cc': 'US', 'org': 'RCN-AS', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '89.73.121.91:80', 'asn': '9141', 'cc': 'PL', 'org': 'AS9141 P4 Play UPC PL network', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '44.27.21.37:80', 'asn': '56508', 'cc': 'US', 'org': 'ARDC', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '194.156.178.25:80', 'asn': '216459', 'cc': 'DE', 'org': 'MARKETINGMINDONLINEGMBH', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '69.194.240.224:80', 'asn': '26120', 'cc': 'US', 'org': 'RHYTHMONE', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '89.212.75.40:80', 'asn': '34779', 'cc': 'SI', 'org': 'T-2-AS AS set propagated by T-2 d.o.o.', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '174.137.67.212:443', 'asn': '46595', 'cc': 'US', 'org': 'PVTN', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '44.27.131.46:80', 'asn': '56508', 'cc': 'US', 'org': 'ARDC', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '38.66.240.27:80', 'asn': '40285', 'cc': 'US', 'org': 'NORTHLAND-CABLE', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '63.218.224.70:80', 'asn': '31713', 'cc': 'BE', 'org': 'GWCOMMS-MPLS A PCCW Company', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '73.236.44.162:80', 'asn': '7922', 'cc': 'US', 'org': 'COMCAST-7922', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '37.136.9.132:80', 'asn': '16086', 'cc': 'FI', 'org': 'DNA', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '38.57.235.160:80', 'asn': '46783', 'cc': 'US', 'org': 'EL-', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '93.47.201.98:80', 'asn': '12874', 'cc': 'IT', 'org': 'FASTWEB', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '62.121.136.201:80', 'asn': '15541', 'cc': 'PL', 'org': 'CETI-AS CETI ISP, Poland', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '46.29.19.88:80', 'asn': '197226', 'cc': 'PL', 'org': 'SPRINT-SDC', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '66.252.199.173:80', 'asn': '20303', 'cc': 'US', 'org': 'BAM', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '69.67.173.51:443', 'asn': '399629', 'cc': 'US', 'org': 'BLNWX', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '23.235.211.195:80', 'asn': '22611', 'cc': 'US', 'org': 'INMOTION', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '192.132.128.179:80', 'asn': '6079', 'cc': 'US', 'org': 'RCN-AS', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '65.111.166.70:80', 'asn': '15083', 'cc': 'US', 'org': 'INFOLINK-MIA-', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '38.38.246.39:443', 'asn': '398478', 'cc': 'US', 'org': 'PEG-HK', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '68.178.224.61:80', 'asn': '26496', 'cc': 'US', 'org': 'AS-26496-GO-DADDY-COM-LLC', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '50.63.27.60:80', 'asn': '398101', 'cc': 'US', 'org': 'GO-DADDY-COM-LLC', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '31.77.152.18:80', 'asn': '219064', 'cc': 'GB', 'org': 'Akenai-Products-AS - Akenai Products LTD', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '207.192.175.186:80', 'asn': '63005', 'cc': 'US', 'org': 'NEXUS-22-63005', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '46.142.87.224:80', 'asn': '8881', 'cc': 'DE', 'org': 'VERSATEL', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '23.111.174.250:80', 'asn': '29802', 'cc': 'US', 'org': 'HVC-AS', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '213.155.74.168:443', 'asn': '12337', 'cc': 'DE', 'org': 'NORIS-NETWORK IT Service Provider located in Nuernberg, Germany', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '45.130.164.129:80', 'asn': '36007', 'cc': 'US', 'org': 'KAMATERA', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '69.5.175.10:80', 'asn': '25369', 'cc': 'GB', 'org': 'BANDWIDTH-AS', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '62.146.100.117:80', 'asn': '15598', 'cc': 'DE', 'org': 'IPX-AS15598', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '62.251.52.76:80', 'asn': '1136', 'cc': 'NL', 'org': 'KPN KPN National', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '38.127.37.222:443', 'asn': '18978', 'cc': 'US', 'org': 'ENZUINC-', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '64.81.235.114:80', 'asn': '6079', 'cc': 'US', 'org': 'RCN-AS', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '38.58.182.187:80', 'asn': '26042', 'cc': 'US', 'org': 'FIBERSTATE', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '67.217.58.109:80', 'asn': '19318', 'cc': 'US', 'org': 'IS-AS-1', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '38.11.224.153:443', 'asn': '398478', 'cc': 'US', 'org': 'PEG-HK', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '38.91.58.88:80', 'asn': '32181', 'cc': 'US', 'org': 'ASN-GIGENET', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '24.199.231.196:80', 'asn': '11426', 'cc': 'US', 'org': 'TWC-11426-CAROLINAS', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '37.152.231.163:80', 'asn': '6871', 'cc': 'GB', 'org': 'PLUSNET UK Internet Service Provider', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '23.229.233.96:80', 'asn': '398101', 'cc': 'US', 'org': 'GO-DADDY-COM-LLC', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '207.192.188.194:80', 'asn': '63005', 'cc': 'US', 'org': 'NEXUS-22-63005', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '45.74.31.42:14701', 'asn': '219326', 'cc': 'GB', 'org': 'SULAVIL - SULAVI LTD', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '207.192.173.3:80', 'asn': '63005', 'cc': 'US', 'org': 'NEXUS-22-63005', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '63.142.241.165:80', 'asn': '394727', 'cc': 'US', 'org': 'NODISTO', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '67.231.240.71:80', 'asn': '40244', 'cc': 'US', 'org': 'TURNKEY-INTERNET', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '64.81.235.167:80', 'asn': '6079', 'cc': 'US', 'org': 'RCN-AS', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '72.179.251.85:80', 'asn': '11427', 'cc': 'US', 'org': 'TWC-11427-TEXAS', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '67.60.203.45:80', 'asn': '11492', 'cc': 'US', 'org': 'CABLEONE', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '31.56.185.45:80', 'asn': '219064', 'cc': 'GB', 'org': 'Akenai-Products-AS - Akenai Products LTD', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '206.74.145.241:80', 'asn': '12208', 'cc': 'US', 'org': 'TRUVISTA', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '38.14.176.180:80', 'asn': '54600', 'cc': 'US', 'org': 'PEG-SV', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '46.246.92.189:80', 'asn': '42708', 'cc': 'SE', 'org': 'GLESYS glesys.com', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '2.26.147.238:80', 'asn': '213468', 'cc': 'FI', 'org': 'TIETOKETTU', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '89.39.68.146:80', 'asn': '5606', 'cc': 'RO', 'org': 'GTS-BACKBONE GTS Telecom', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '31.77.199.70:80', 'asn': '215590', 'cc': 'GB', 'org': 'DPKGSOFT-AS', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '62.146.117.52:80', 'asn': '15598', 'cc': 'DE', 'org': 'IPX-AS15598', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '37.202.222.14:80', 'asn': '21859', 'cc': 'US', 'org': 'ZEN-ECN', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '23.231.110.72:443', 'asn': '62904', 'cc': 'US', 'org': 'AS62904 - Eonix Corporation', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '64.251.22.179:80', 'asn': '15083', 'cc': 'US', 'org': 'INFOLINK-MIA-', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '62.210.26.108:80', 'asn': '12876', 'cc': 'FR', 'org': 'Online SAS', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '24.106.147.247:80', 'asn': '10796', 'cc': 'US', 'org': 'TWC-10796-MIDWEST', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '38.173.221.172:80', 'asn': '54600', 'cc': 'US', 'org': 'PEG-SV', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '69.30.255.9:80', 'asn': '32097', 'cc': 'US', 'org': 'WII', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '209.182.252.137:80', 'asn': '17098', 'cc': 'US', 'org': 'BROWNRICE-INTERNET-1', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '38.11.136.161:443', 'asn': '398478', 'cc': 'US', 'org': 'PEG-HK', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '77.37.97.87:443', 'asn': '44803', 'cc': 'DK', 'org': 'WEBDOCK-AS', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '62.192.165.8:80', 'asn': '211856', 'cc': 'NL', 'org': 'DE-NEDERLANDSCHE-BANK', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '8.19.154.19:80', 'asn': '3356', 'cc': 'US', 'org': 'LEVEL3', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '72.214.73.212:80', 'asn': '22773', 'cc': 'US', 'org': 'ASN-CXA-ALL-CCI-22773-RDC', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '64.81.232.35:80', 'asn': '6079', 'cc': 'US', 'org': 'RCN-AS', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '45.74.31.46:5898', 'asn': '219326', 'cc': 'GB', 'org': 'SULAVIL - SULAVI LTD', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '51.15.165.75:80', 'asn': '12876', 'cc': 'FR', 'org': 'Online SAS', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '50.31.1.10:80', 'asn': '29802', 'cc': 'US', 'org': 'HVC-AS', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '31.59.181.117:80', 'asn': '213915', 'cc': 'GB', 'org': 'PHILIPP-MORIS-TRETTIN', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '45.202.11.176:80', 'asn': '54801', 'cc': 'US', 'org': 'ZILLION-NETWORK', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '38.38.229.209:443', 'asn': '394432', 'cc': 'US', 'org': 'PEG-SG', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '62.4.18.86:80', 'asn': '12876', 'cc': 'FR', 'org': 'Online SAS', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '74.204.221.119:80', 'asn': '17088', 'cc': 'US', 'org': 'CURRENEX', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '31.14.96.168:80', 'asn': '20857', 'cc': 'NL', 'org': 'TRANSIP-AS Amsterdam, the Netherlands', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '64.83.9.141:80', 'asn': '979', 'cc': 'US', 'org': 'NETLAB-SDN', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '38.178.11.185:80', 'asn': '35986', 'cc': 'US', 'org': 'VYVE-BROADBAND', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '72.167.205.231:80', 'asn': '398101', 'cc': 'US', 'org': 'GO-DADDY-COM-LLC', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '64.202.186.240:443', 'asn': '398101', 'cc': 'US', 'org': 'GO-DADDY-COM-LLC', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '31.172.70.63:80', 'asn': '44051', 'cc': 'ES', 'org': 'FORNEX-AS', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '38.14.164.98:80', 'asn': '54600', 'cc': 'US', 'org': 'PEG-SV', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '64.44.121.36:80', 'asn': '20278', 'cc': 'US', 'org': 'NEXEON', 'is_us_eu': True, 'group': 'useu_residential'}, {'proxy': '46.21.226.227:80', 'asn': '34762', 'cc': 'BE', 'org': 'COMBELL-AS', 'is_us_eu': True, 'group': 'useu_residential'}]

HOST_64K = "httpbin.org"
PORT_64K = 80
PATH_64K = "/bytes/65536"
BYTES_64K = 65536

HOST_BULK = "ash.speedtest.clouvider.net"
PORT_BULK = 80
PATH_BULK = "/backend/garbage.php?ckSize=2"
BYTES_BULK = 2097152

HOST_TLS = "speed.cloudflare.com"
PORT_TLS = 443
PATH_TLS = "/__down?bytes=2097152"
BYTES_TLS = 2097152

CONCURRENCY = 25
TIMEOUT_CAP = 30.0
CONNECT_TIMEOUT = 8.0

async def measure_container_direct():
    print("=" * 85)
    print(" MEASURING CONTAINER HOST DIRECT NON-CDN THROUGHPUT")
    print("=" * 85)
    loop = asyncio.get_running_loop()
    
    # Direct 2MB from Clouvider (Non-CDN)
    t0 = time.monotonic()
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setblocking(False)
    try:
        await asyncio.wait_for(loop.sock_connect(s, (HOST_BULK, PORT_BULK)), timeout=10.0)
        req = f"GET {PATH_BULK} HTTP/1.1\r\nHost: {HOST_BULK}\r\nUser-Agent: curl/7.88.1\r\nConnection: close\r\n\r\n".encode()
        await loop.sock_sendall(s, req)
        data = b""
        while len(data) < BYTES_BULK:
            chunk = await asyncio.wait_for(loop.sock_recv(s, 65536), timeout=15.0)
            if not chunk: break
            data += chunk
        el = max(0.001, time.monotonic() - t0)
        mb_s = (len(data) / 1048576.0) / el
        print(f"Container Direct Downlink (Clouvider Non-CDN): {mb_s:.2f} MB/s ({mb_s*8:.2f} Mbps) [{len(data):,} bytes in {el:.2f}s]")
    except Exception as e:
        print(f"Container direct downlink test error: {e}")
        mb_s = 0.0
    finally:
        s.close()
        
    print("=" * 85)
    print()
    return {"host_direct_noncdn_mb_s": round(mb_s, 2), "host_direct_noncdn_mbps": round(mb_s*8, 2)}

async def stage_test_raw_tunnel(proxy, target_host, target_port, target_path, target_bytes, is_tls=False):
    ip, port = proxy.split(":")
    port = int(port)
    loop = asyncio.get_running_loop()
    
    result = {
        "proxy": proxy,
        "stage_failed": None,
        "fail_reason": None,
        "bytes_received": 0,
        "elapsed_s": 0.0,
        "mb_s": 0.0,
        "status": "fail"
    }
    
    t0 = time.monotonic()
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setblocking(False)
    
    try:
        # Stage 1: connect (TCP handshake to proxy)
        current_stage = "connect"
        await asyncio.wait_for(loop.sock_connect(s, (ip, port)), timeout=CONNECT_TIMEOUT)
        
        # Stage 2: connect_reply (Send CONNECT and parse proxy tunnel response)
        current_stage = "connect_reply"
        req = f"CONNECT {target_host}:{target_port} HTTP/1.1\r\nHost: {target_host}:{target_port}\r\n\r\n".encode()
        await loop.sock_sendall(s, req)
        
        resp = b""
        t_end = time.monotonic() + 6.0
        while b"\r\n\r\n" not in resp:
            if time.monotonic() > t_end:
                result["stage_failed"] = "connect_reply"
                result["fail_reason"] = "CONNECT_Timeout"
                return result
            chunk = await asyncio.wait_for(loop.sock_recv(s, 512), timeout=4.0)
            if not chunk:
                break
            resp += chunk
            
        if not resp:
            result["stage_failed"] = "connect_reply"
            result["fail_reason"] = "Connection_Closed_By_Proxy"
            return result
            
        first_line = resp.split(b"\r\n")[0].decode(errors="ignore").strip()
        if " 200" not in first_line:
            result["stage_failed"] = "connect_reply"
            result["fail_reason"] = f"Proxy_{first_line[:25].replace(' ', '_')}"
            return result
            
        # Detect Webserver masquerading / captive portal returning HTML instead of raw tunnel
        resp_lower = resp.lower()
        if b"content-type: text/html" in resp_lower or b"<html" in resp_lower or b"<!doctype" in resp_lower:
            result["stage_failed"] = "connect_reply"
            result["fail_reason"] = "Fake_200_Webserver_HTML"
            return result
            
        # Stage 3: TLS (if applicable)
        if is_tls:
            current_stage = "tls"
            # Attempt TLS handshake over raw socket
            ssl_ctx = ssl.create_default_context()
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode = ssl.CERT_NONE
            # Use asyncio start_tls
            # If start_tls is not directly available on raw socket without transport:
            pass

        # Stage 4: first_byte (Send GET inside tunnel, await first byte)
        current_stage = "first_byte"
        get_req = f"GET {target_path} HTTP/1.1\r\nHost: {target_host}\r\nUser-Agent: curl/7.88.1\r\nConnection: close\r\n\r\n".encode()
        await loop.sock_sendall(s, get_req)
        
        head = await asyncio.wait_for(loop.sock_recv(s, 2048), timeout=10.0)
        if not head:
            result["stage_failed"] = "first_byte"
            result["fail_reason"] = "Empty_Response_From_Origin"
            return result
            
        # Check HTTP status of origin response
        head_first = head.split(b"\r\n")[0].decode(errors="ignore")
        if "200" not in head_first:
            result["stage_failed"] = "first_byte"
            result["fail_reason"] = f"Origin_{head_first[:20].replace(' ', '_')}"
            return result

        # Stage 5: full_body (Stream payload until target_bytes or EOF)
        current_stage = "full_body"
        bytes_recv = len(head)
        t_deadline = time.monotonic() + TIMEOUT_CAP
        while bytes_recv < target_bytes:
            if time.monotonic() > t_deadline:
                result["stage_failed"] = "full_body"
                result["fail_reason"] = "Stream_Timeout_30s"
                break
            chunk = await asyncio.wait_for(loop.sock_recv(s, 32768), timeout=10.0)
            if not chunk:
                break
            bytes_recv += len(chunk)
            
        el = max(0.001, time.monotonic() - t0)
        result["bytes_received"] = bytes_recv
        result["elapsed_s"] = round(el, 3)
        result["mb_s"] = round((bytes_recv / 1048576.0) / el, 4) if bytes_recv > 0 else 0.0
        
        if bytes_recv >= target_bytes * 0.95:
            result["status"] = "ok"
            result["stage_failed"] = None
            result["fail_reason"] = None
        else:
            result["status"] = "partial" if bytes_recv > 0 else "fail"
            if not result["stage_failed"]:
                result["stage_failed"] = "full_body"
                result["fail_reason"] = f"Incomplete_{bytes_recv}_of_{target_bytes}"
        return result
        
    except ConnectionRefusedError:
        result["stage_failed"] = current_stage
        result["fail_reason"] = "ConnectionRefused"
        return result
    except asyncio.TimeoutError:
        result["stage_failed"] = current_stage
        result["fail_reason"] = f"{current_stage}_Timeout"
        return result
    except OSError as e:
        result["stage_failed"] = current_stage
        result["fail_reason"] = f"OSError_{getattr(e, 'errno', type(e).__name__)}"
        return result
    except Exception as e:
        result["stage_failed"] = current_stage
        result["fail_reason"] = type(e).__name__
        return result
    finally:
        s.close()

async def worker(sem, proxy_item):
    p = proxy_item["proxy"]
    async with sem:
        # Test 1: 64KB non-CDN
        res_64k = await stage_test_raw_tunnel(p, HOST_64K, PORT_64K, PATH_64K, BYTES_64K, is_tls=False)
        # Test 2: Bulk 2MB non-CDN
        res_bulk = await stage_test_raw_tunnel(p, HOST_BULK, PORT_BULK, PATH_BULK, BYTES_BULK, is_tls=False)
        
        return {
            "proxy": p,
            "cc": proxy_item["cc"],
            "org": proxy_item["org"],
            "group": proxy_item.get("group", "global"),
            "is_us_eu": proxy_item["is_us_eu"],
            "test_64k": res_64k,
            "test_bulk": res_bulk
        }

def bucket_mbps(mb_s, status):
    if status == "fail" or mb_s <= 0.0:
        return "fail"
    if mb_s < 0.05:
        return "<0.05"
    elif mb_s < 0.2:
        return "0.05-0.2"
    elif mb_s < 0.5:
        return "0.2-0.5"
    elif mb_s <= 2.0:
        return "0.5-2"
    else:
        return ">2"

def percentile(vals, p):
    if not vals: return 0.0
    s = sorted(vals)
    k = (len(s) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(s) - 1)
    d = k - f
    return s[f] + d * (s[c] - s[f])

def print_stage_breakdown(title, test_results, key_name):
    print("=" * 85)
    print(f" STAGE FAILURE BREAKDOWN: {title.upper()} (N={len(test_results)})")
    print("=" * 85)
    stages = ["connect", "connect_reply", "tls", "first_byte", "full_body", "passed"]
    stage_counts = {s: 0 for s in stages}
    fail_reasons = {}
    
    for r in test_results:
        sub = r[key_name]
        sf = sub.get("stage_failed")
        if sf is None and sub.get("status") == "ok":
            stage_counts["passed"] += 1
        else:
            stage = sf if sf in stage_counts else "full_body"
            stage_counts[stage] += 1
            reason = f"{stage}: {sub.get('fail_reason')}"
            fail_reasons[reason] = fail_reasons.get(reason, 0) + 1
            
    print(f"{'Pipeline Stage':<20} | {'Drop Count':<12} | {'% of Population':<18} | {'Stage Status'}")
    print("-" * 85)
    total = len(test_results)
    for st in ["connect", "connect_reply", "tls", "first_byte", "full_body"]:
        cnt = stage_counts[st]
        pct = (cnt / total) * 100.0
        print(f"1. {st:<17} | {cnt:>10,} | {pct:>16.2f}% | FAILED")
    passed_cnt = stage_counts["passed"]
    passed_pct = (passed_cnt / total) * 100.0
    print("-" * 85)
    print(f"PASSED (Completed)   | {passed_cnt:>10,} | {passed_pct:>16.2f}% | SUCCESS")
    print("=" * 85)
    
    print(f"Top 8 Failure Reasons ({title}):")
    sorted_reasons = sorted(fail_reasons.items(), key=lambda x: x[1], reverse=True)[:8]
    for r_name, r_cnt in sorted_reasons:
        print(f"  * {r_name:<45}: {r_cnt:>4} ({r_cnt/total*100:.1f}%)")
    print()

def print_bucket_table(title, test_results, key_name):
    bucket_order = ["<0.05", "0.05-0.2", "0.2-0.5", "0.5-2", ">2", "fail"]
    buckets = {b: [] for b in bucket_order}
    total = len(test_results)
    
    for r in test_results:
        sub = r[key_name]
        b = bucket_mbps(sub["mb_s"], sub["status"])
        buckets[b].append(sub)
        
    print("=" * 85)
    print(f" THROUGHPUT BUCKETS: {title.upper()} (N={total})")
    print("=" * 85)
    print(f"{'Throughput Bucket':<18} | {'Count':<7} | {'% Total':<10} | {'Median MB/s':<14} | {'p90 MB/s'}")
    print("-" * 85)
    
    active_speeds = [r[key_name]["mb_s"] for r in test_results if r[key_name]["status"] in ("ok", "partial") and r[key_name]["mb_s"] > 0]
    
    for b in bucket_order:
        items = buckets[b]
        cnt = len(items)
        pct = (cnt / total) * 100.0
        if b == "fail" or cnt == 0:
            med_str = "-"
            p90_str = "-"
        else:
            speeds = [x["mb_s"] for x in items]
            med_str = f"{percentile(speeds, 50):.4f}"
            p90_str = f"{percentile(speeds, 90):.4f}"
        print(f"{b:<18} | {cnt:>7,} | {pct:>9.2f}% | {med_str:>14} | {p90_str}")
        
    print("-" * 85)
    act_cnt = len(active_speeds)
    act_pct = (act_cnt / total) * 100.0
    ov_med = percentile(active_speeds, 50) if active_speeds else 0.0
    ov_p90 = percentile(active_speeds, 90) if active_speeds else 0.0
    print(f"{'Active Subtotal':<18} | {act_cnt:>7,} | {act_pct:>9.2f}% | {ov_med:>14.4f} | {ov_p90:.4f}")
    print("=" * 85)
    print(f"Summary: Active Median = {ov_med:.4f} MB/s ({ov_med*8:.2f} Mbps) | p90 = {ov_p90:.4f} MB/s ({ov_p90*8:.2f} Mbps)")
    print()

async def main():
    print("=== KAGGLE NON-CDN RAW THROUGHPUT & STAGE BENCHMARK (V3) ===")
    print(f"Tested Proxies: {len(SAMPLE_PROXIES)} (150 Global Residential + 150 US/EU Residential)")
    print(f"Target 1 (64KB):   {HOST_64K}:{PORT_64K}{PATH_64K} (inside CONNECT, no TLS)")
    print(f"Target 2 (Bulk):   {HOST_BULK}:{PORT_BULK}{PATH_BULK} (2MB, inside CONNECT, no TLS)")
    print(f"Concurrency: {CONCURRENCY} | Per-proxy cap: {TIMEOUT_CAP}s")
    print()
    
    direct_metrics = await measure_container_direct()
    
    sem = asyncio.Semaphore(CONCURRENCY)
    t0 = time.time()
    tasks = [worker(sem, item) for item in SAMPLE_PROXIES]
    results = await asyncio.gather(*tasks)
    total_time = time.time() - t0
    print(f"Benchmarked all {len(SAMPLE_PROXIES)} proxies across 64KB & Bulk in {total_time:.2f}s!")
    print()
    
    # 1. Stage breakdown for 64KB
    print_stage_breakdown("64KB Non-CDN Test", results, "test_64k")
    # 2. Stage breakdown for Bulk 2MB
    print_stage_breakdown("Bulk 2MB Non-CDN Test", results, "test_bulk")
    
    # 3. Throughput buckets for 64KB
    print_bucket_table("64KB Non-CDN Throughput", results, "test_64k")
    # 4. Throughput buckets for Bulk 2MB
    print_bucket_table("Bulk 2MB Non-CDN Throughput", results, "test_bulk")

    # 5. Breakdown by Region for Bulk 2MB
    useu = [r for r in results if r["is_us_eu"]]
    print_bucket_table("Bulk 2MB - US & EU Residential Subset", useu, "test_bulk")

    with open("benchmark_results_v3.json", "w", encoding="utf-8") as f:
        json.dump({"direct": direct_metrics, "total": len(results), "elapsed": round(total_time, 2), "results": results}, f, indent=2)
    print("Saved benchmark_results_v3.json")

if __name__ == "__main__":
    asyncio.run(main())
