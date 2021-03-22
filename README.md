# Setup instructions.

## VirtualEnv
This has been tested on python 3.8.5, but more modern compatible versions should work.
I strongly suggest you run this system from within a virtualenv.

```shell
cd ./desired/working/directory/
python3.8 -m venv ./d4a-venv/
source ./d4a-venv/bin/activate
```

## Requirements
Install requirements for this project and for avatar2. 

* pykush and matplotlib are optional
    * The system will work fine without either or both.
* Note that pykush may not be up-to-date on pip.
    * Manual installation can be done as follows:
```shell
# Ensure you are in VENV
pip install git+https://github.com/Yepkit/pykush.git
```

### D4A
You will need these requirements (see also requirements.txt)
```
numpy~=1.19.4
scikit-learn~=0.23.2
pykush~=0.3.0
matplotlib~=3.3.3
```

### Avatar2
You will need these to run avatar2 (also included in requirements.txt)
```
pyserial~=3.5
intervaltree~=3.1.0
capstone~=4.0.2
unicorn~=1.0.2
enum34~=1.1.10
configparser~=5.0.1
npyscreen~=4.10.5
pygdbmi~=0.10.0.0
parse~=1.18.0
PyLink~=0.3.3
setuptools~=51.0.0
keystone-engine==0.9.2
```

Before running this system ensure avatar2 is available, either install it to your virtual environment or ensure it is on
the python-path.
```shell
export PYTHONPATH=~/path/to/avatar2
```