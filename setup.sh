#!/usr/bin/bash
cd ~
sudo mkdir kuma
sudo python -m venv kuma
source kuma/bin/activate
pip install -r ~/kumakita/requirements.txt
exit
