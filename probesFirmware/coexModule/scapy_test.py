from scapy.all import *

# Impostiamo gli IP e i MAC (sostituisci con i tuoi valori)
client_ip = "10.13.150.215"
server_ip = "81.57.14.202"
client_mac = "02:50:f4:00:00:01"
server_mac = "02:50:f3:00:00:00"

# Definisci la porta di destinazione
server_port = 50505
client_port = 42846

# Creiamo il pacchetto SYN (inizio connessione)
syn = IP(src=client_ip, dst=server_ip)/TCP(sport=client_port, dport=server_port, flags="S", seq=199767285, window=33120, options=[('MSS', 1380), ('SACKOK', b'')])

# Invia il pacchetto SYN e cattura la risposta (SYN-ACK)
synack = sr1(syn)

# Creiamo il pacchetto ACK per completare l'handshake TCP
ack = IP(src=client_ip, dst=server_ip)/TCP(sport=client_port, dport=server_port, flags="A", seq=synack.ack, ack=synack.seq + 1)

# Invio del pacchetto ACK
send(ack)

# Pacchetto di dati che simula la GET (esempio di dati, cambia a seconda di ciò che vuoi inviare)
# Questo dovrebbe essere un pacchetto "PUSH" (con la flag P)
data = "GET / HTTP/1.1\r\nHost: moisturemonitor.ddns.net\r\n\r\n"  # Cambia questa parte in base alla GET che vuoi replicare
payload = IP(src=client_ip, dst=server_ip)/TCP(sport=client_port, dport=server_port, flags="PA", seq=synack.ack + 1, ack=synack.seq + 1)/Raw(load=data)

# Invia il pacchetto di dati
send(payload)

# Invia pacchetto ACK per confermare la ricezione del dato
ack_data = IP(src=client_ip, dst=server_ip)/TCP(sport=client_port, dport=server_port, flags="A", seq=synack.ack + len(data), ack=synack.seq + 1)
send(ack_data)

# Chiudiamo la connessione con il pacchetto FIN
fin = IP(src=client_ip, dst=server_ip)/TCP(sport=client_port, dport=server_port, flags="F", seq=synack.ack + len(data), ack=synack.seq + 1)
send(fin)

# Riceviamo il pacchetto ACK finale per confermare la chiusura della connessione
finack = sr1(fin)

# Concludiamo la chiusura della connessione
ack_fin = IP(src=client_ip, dst=server_ip)/TCP(sport=client_port, dport=server_port, flags="A", seq=finack.ack, ack=finack.seq + 1)
send(ack_fin)

print("Connessione replicata con successo!")
