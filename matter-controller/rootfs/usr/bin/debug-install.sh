#!/bin/sh

echo "=== Matter Controller Debug Info ==="
echo "System Python version:"
python3 --version
echo ""
echo "Installed packages:"
pip3 list
echo ""
echo "System info:"
uname -a
echo ""
echo "Directory structure:"
ls -la /matter_controller
echo ""
echo "Data directory:"
ls -la /data
echo ""
echo "=== End Debug Info ==="
