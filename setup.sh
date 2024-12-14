#!/usr/bin/bash
cd ~
sudo mkdir kuma
python -m venv kuma
source kuma/bin/activate
pip install -r ~/AITRIOS/requirements.txt
exit