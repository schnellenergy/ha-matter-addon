#!/bin/bash

echo "=== Matter Controller Debug Info ==="
echo "System Python version:"
python3 --version
echo ""
echo "Virtual environment Python version:"
source /opt/venv/bin/activate
python --version
echo ""
echo "Virtual environment path:"
echo $VIRTUAL_ENV
echo ""
echo "Installed packages in virtual environment:"
pip list
echo ""
echo "System info:"
uname -a
echo ""
echo "Directory structure:"
ls -la /matter_controller
echo ""
echo "Matter Server directory:"
ls -la /opt/python-matter-server
echo ""
echo "Virtual environment directory:"
ls -la /opt/venv
echo ""
echo "Data directory:"
ls -la /data
echo ""
echo "=== End Debug Info ==="
