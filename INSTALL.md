# Installation instructions

Documenting here in case I need to deploy again, or if somebody else uses this software.

## Set up certbot, get certificates, and set up nginx

I flailed quite a bit here, it definitely started with these commands

```
sudo yum install nginx
sudo yum install python3-pip
sudo pip3 install certbot certbot-nginx
```

but then I had problems with the nginx conf somehow and couldn't get certbot to work.

I think for some reason the nginx conf was broken, eventually I copied the default nginx conf
and then certbot was able to run. I think the successful command line was 

```
sudo certbot --nginx -d verbal-cli.xyz,www.verbal-cli.xyz
```

In any case, the final version of  `/etc/nginx/nginx.conf` is

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

This does not include periodic renewals, would be fun when that's needed.

## Set up oauth2-proxy

Install:

```
OAUTH2_PROXY_VERSION=$(curl -s https://api.github.com/repos/oauth2-proxy/oauth2-proxy/releases/latest | grep "tag_name" | cut -d '"' -f 4 | sed 's/v//')
wget https://github.com/oauth2-proxy/oauth2-proxy/releases/download/v${OAUTH2_PROXY_VERSION}/oauth2-proxy-v${OAUTH2_PROXY_VERSION}.linux-amd64.tar.gz
tar xzvf oauth2-proxy-v${OAUTH2_PROXY_VERSION}.linux-amd64.tar.gz
sudo mv oauth2-proxy-v${OAUTH2_PROXY_VERSION}.linux-amd64/oauth2-proxy /usr/local/bin/
sudo chmod +x /usr/local/bin/oauth2-proxy
```

Configure:

```
sudo mkdir /etc/oauth2-proxy
sudo nano /etc/oauth2-proxy/oauth2-proxy.cfg
sudo nano /etc/oauth2-proxy/authenticated-emails
sudo mv logo.png /etc/oauth2-proxy/
```

```
sudo useradd --system --no-create-home --shell /sbin/nologin oauth2proxy
sudo chown oauth2proxy:oauth2proxy /etc/oauth2-proxy/*
sudo chmod 600 /etc/oauth2-proxy/*
sudo mkdir -p /var/lib/oauth2-proxy
sudo chown oauth2proxy:oauth2proxy /var/lib/oauth2-proxy
sudo chmod 700 /var/lib/oauth2-proxy

sudo tee /etc/systemd/system/oauth2-proxy.service > /dev/null <<EOF
[Unit]
Description=oauth2-proxy
After=network.target

[Service]
ExecStart=/usr/local/bin/oauth2-proxy --config=/etc/oauth2-proxy/oauth2-proxy.cfg
Restart=always
User=oauth2proxy
Group=oauth2proxy
WorkingDirectory=/var/lib/oauth2-proxy

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable oauth2-proxy
sudo systemctl start oauth2-proxy
```

Verify running with no errors:

```
sudo journalctl -u oauth2-proxy -f
```

## Set up docker

```
sudo yum install -y docker
sudo systemctl start docker
sudo systemctl enable docker

docker build -t verbal .
docker run -p 8501:8501 -it verbal
```
