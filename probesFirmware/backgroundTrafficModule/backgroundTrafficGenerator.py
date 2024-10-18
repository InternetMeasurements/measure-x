import os.path
import subprocess


class BackgroundTrafficGenerator:
    def __init__(self):
        self.cmd = None
        self.process = None
        self.pcap_path = None

    def submit_process(self, pcap_path, interface_id = 'eth0'):
        self.pcap_path = pcap_path
        if not os.path.exists(self.pcap_path):
            print(f"WARNING: File pcap not found! Check given path -> {pcap_path}")
        self.cmd = ['wsl', 'sudo', 'tcpreplay', '--verbose', '--intf1={}'.format(interface_id), self.pcap_path]
        self.process = subprocess.Popen(self.cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        print("TCPReplay process submitted")

    def execute_process(self):
        if not os.path.exists(self.pcap_path):
            print(f"ERROR: File pcap not found!")
            return
        try:
            print("Execution...")
            result = subprocess.run(self.cmd, capture_output=True, text=True, check=True)
            print(f"Output:\n{result.stdout}")
        except subprocess.CalledProcessError as e:
            print(f"Errore durante l'esecuzione di tcpreplay:\n{e.stderr}")

    def stop_tcpreplay_execution(self):
        self.process.terminate() # Vediamo se posso terminarlo con calma o devo inviare un SIGKILL o SIGTERM
        exit_code = self.process.wait()  # Attendere che il processo finisca
        print(f"tcpreplay terminato con codice di uscita: {exit_code}")