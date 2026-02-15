# systemd Deployment (optional, Linux only)

Copy service file:

```bash
sudo cp /Users/sg_mac/lbplate/deploy/systemd/lbplate.service /etc/systemd/system/lbplate.service
sudo systemctl daemon-reload
sudo systemctl enable lbplate
sudo systemctl restart lbplate
sudo systemctl status lbplate --no-pager
```

Logs:

```bash
sudo journalctl -u lbplate -f
```
