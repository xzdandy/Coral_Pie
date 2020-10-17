#! /bin/sh

version=4.1.1

sudo apt update

sudo apt install -y libtiff-dev zlib1g-dev
sudo apt install -y libjpeg-dev libpng-dev
sudo apt install -y libavcodec-dev libavformat-dev libswscale-dev libv4l-dev
sudo apt install -y libxvidcore-dev libx264-dev

tar xfv opencv-${version}-armhf.tar.bz2
sudo mv opencv-${version} /opt

sudo cp opencv.pc /usr/lib/arm-linux-gnueabihf/pkgconfig

echo 'export LD_LIBRARY_PATH=/opt/opencv-'"${version}"'/lib:$LD_LIBRARY_PATH' >> ~/.bashrc

sudo ln -s /opt/opencv-${version}/lib/python3.7/dist-packages/cv2 /usr/lib/python3/dist-packages/cv2
