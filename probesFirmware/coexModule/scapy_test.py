from scapy.all import Ether, IP, UDP, Raw, sendpfast

# Parametri MAC e IP
src_mac = "02:50:f4:00:00:03"  # MAC della probe3
dst_mac = "02:50:f3:00:00:00"  # MAC della base station 5G
src_ip = "10.0.0.3"  # IP sorgente della probe3
dst_ip = "10.0.0.2"  # IP destinazione (probe2 o il server)

# Esempio di traffico (modifica a seconda dei dati catturati)
pkt = Ether(src=src_mac, dst=dst_mac) / IP(src=src_ip, dst=dst_ip) / UDP(sport=30000, dport=5001) / Raw(RandString(size=50))

# Parametri di invio
rate = 100  # Velocità di invio in Mbps (personalizza in base alle tue necessità)
n_pkts = 10  # Numero di pacchetti (usa quello che ti serve)

# Invio del traffico
sendpfast(pkt, mbps=rate, loop=n_pkts)
