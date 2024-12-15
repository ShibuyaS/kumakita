cd ~/kumakita
echo 'installing venv'
sudo python -m venv kuma
source kuma/bin/activate
echo 'installing dependencies'
pip install -r requirements.txt
exit
