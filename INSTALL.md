# Installation instructions

Documenting here in case I need to deploy again, or if somebody else uses this software.

Get a fresh EC2 with Ubuntu 24.04.

## Basic setup
```
sudo apt update
sudo apt upgrade
sudo apt install nginx python3 python3-venv libaugeas0 docker.io docker-compose-v2 unzip
```

## SSL certificate

Install and run Certbot for the initial certificate
```
sudo python3 -m venv /opt/certbot/
sudo /opt/certbot/bin/pip install --upgrade pip
sudo /opt/certbot/bin/pip install certbot certbot-nginx
sudo ln -s /opt/certbot/bin/certbot /usr/bin/certbot
sudo certbot --nginx
```

Then run `sudo crontab -e` and add the following line for periodic renewal:
```
0 0,12 * * * root /opt/certbot/bin/python -c 'import random; import time; time.sleep(random.random() * 3600' && sudo certbot renew -q
```

## Install Verbal

First get the code
```
git clone https://github.com/amirlb/verbal.git
cd verbal/
```

Create an `oauth2-proxy` directory with `.env` for the OpenID secrets, and
`authenticated-emails.txt` for the access list.

Add the AI API secrets in
`app/.env`.

## Setup nginx

Put this in `/etc/nginx/nginx.conf`, with the correct domain. Redirects HTTP
to HTTPS and proxies to the docker container.

```
events {
}

http {
    server {
        listen 80;
        server_name verbal-cli.xyz www.verbal-cli.xyz;
        return 301 https://$host$request_uri;
    }

    server {
        listen 443 ssl;
        server_name verbal-cli.xyz www.verbal-cli.xyz;
        ssl_certificate /etc/letsencrypt/live/verbal-cli.xyz/fullchain.pem;
        ssl_certificate_key /etc/letsencrypt/live/verbal-cli.xyz/privkey.pem;
        ssl_trusted_certificate /etc/letsencrypt/live/verbal-cli.xyz/chain.pem;

        location / {
            proxy_pass http://localhost:4180;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;

            # Websocket stuff
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
        }
    }
}
```

## Upgrade / launch Verbal

Update:
```
git pull
```

Run:
```
sudo docker compose up --build
```
