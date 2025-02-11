from flask import Flask
import subprocess

app = Flask(__name__)

VALID_SERVICES = ["verbal", "verbal-staging"]

@app.route('/deploy/<service>', methods=['POST'])
def deploy(service):
    if service not in VALID_SERVICES:
        return "Invalid service", 400

    try:
        # Stop, rebuild and start the service
        subprocess.run(["sudo", "docker", "compose", "stop", service], check=True)
        subprocess.run(["sudo", "docker", "compose", "build", service], check=True)
        subprocess.run(["sudo", "docker", "compose", "up", "-d", service], check=True)

        return f"Service {service} redeployed successfully"
    except subprocess.CalledProcessError as e:
        return str(e), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
