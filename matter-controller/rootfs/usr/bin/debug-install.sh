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
echo "GLIBC version:"
ldd --version | head -n 1
echo ""
echo "Library dependencies for Matter Server:"
if [ -f "/opt/venv/lib/python3.11/site-packages/chip/_ChipDeviceCtrl.so" ]; then
    ldd /opt/venv/lib/python3.11/site-packages/chip/_ChipDeviceCtrl.so
else
    echo "ChipDeviceCtrl.so not found"
    find /opt/venv -name "_ChipDeviceCtrl.so" 2>/dev/null
fi
echo ""
echo "Directory structure:"
ls -la /matter_controller
echo ""
echo "Matter Server directory:"
ls -la /opt/python-matter-server 2>/dev/null || echo "Directory not found"
echo ""
echo "Virtual environment directory:"
ls -la /opt/venv
echo ""
echo "Data directory:"
ls -la /data
echo ""
echo "Testing Matter Server import:"
python -c "import matter_server; print('Matter Server import successful')" 2>/dev/null || echo "Matter Server import failed"
echo ""
echo "=== End Debug Info ==="
