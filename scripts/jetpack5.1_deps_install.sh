#!/bin/bash

# install pytorch
sudo apt update
sudo apt install -y \
    libjpeg-dev \
    libopenmpi-dev \
    libavcodec-dev \
    libavformat-dev \
    libswscale-dev \
    libpng-dev

sudo apt install -y \
    libx264-dev \
    libfaac-dev \
    libxvidcore-dev

sudo apt install -y libjpeg-dev zlib1g-dev libopenblas-dev libopenmpi-dev libomp-dev
pip3 install --upgrade pip
pip3 install wheel setuptools
pip3 install --upgrade pillow
pip3 install "numpy<2"

git clone --recursive --branch v2.1.0 https://github.com/pytorch/pytorch
cd pytorch
pip3 install -r requirements.txt
export USE_CUDA=1
export USE_CUDNN=1
export USE_MKLDNN=0
export USE_NCCL=1
export USE_DISTRIBUTED=1
export USE_QNNPACK=0
export USE_PYTORCH_QNNPACK=0
export TORCH_CUDA_ARCH_LIST="7.2;8.7"
export PYTORCH_BUILD_VERSION=2.1.0
export PYTORCH_BUILD_NUMBER=1

python3 setup.py bdist_wheel
pip3 install dist/*.whl
cd ..

git clone --branch v0.16.0 https://github.com/pytorch/vision.git
cd vision
export BUILD_VERSION=0.16.0
export TORCHVISION_USE_VIDEO_CODEC=ON
export FORCE_CUDA=1
export MAX_JOBS=4

python3 setup.py bdist_wheel
pip3 install dist/*.whl
cd ..


#install PyQt5
pip install PyQt-builder sip
wget https://files.pythonhosted.org/packages/0e/07/c9ed0bd428df6f87183fca565a79fee19fa7c88c7f00a7f011ab4379e77a/PyQt5-5.15.11.tar.gz
tar -xvzf PyQt5-5.15.11.tar.gz
cd PyQt5-5.15.11
sip-install
cd ..

pip uninstall sip  # sic!
wget https://files.pythonhosted.org/packages/01/79/086b50414bafa71df494398ad277d72e58229a3d1c1b1c766d12b14c2e6d/pyqt5_sip-12.17.0.tar.gz
tar -xvzf pyqt5_sip-12.17.0.tar.gz
cd pyqt5_sip-12.17.0
python setup.py install
cd ..


# install opencv stage 1
git clone https://github.com/opencv/opencv.git
git clone https://github.com/opencv/opencv_contrib.git
mkdir -p opencv/build
cd opencv_contrib
git checkout 4.11.0
cd ../opencv
git checkout 4.11.0
cd build
cmake -D WITH_CUDA=ON -D WITH_CUDNN=ON -D CUDA_ARCH_BIN="7.2,8.7" -D CUDA_ARCH_PTX="" -DBUILD_opencv_python3=ON -D OPENCV_GENERATE_PKGCONFIG=ON -D OPENCV_EXTRA_MODULES_PATH=../../opencv_contrib/modules -D WITH_GSTREAMER=ON -D WITH_LIBV4L=ON -D BUILD_opencv_python3=ON -D BUILD_TESTS=OFF -D BUILD_PERF_TESTS=OFF -D BUILD_EXAMPLES=OFF -D CMAKE_BUILD_TYPE=RELEASE -D CMAKE_INSTALL_PREFIX=/usr/local ..
make -j4
sudo make install
echo 'export LD_LIBRARY_PATH=/usr/local/lib:$LD_LIBRARY_PATH' >> ~/.bashrc
source ~/.bashrc
cd ../../

# install opencv stage 2
git clone https://github.com/opencv/opencv-python.git
cd opencv-python

export CMAKE_ARGS="-DWITH_CUDA=ON -DWITH_CUDNN=ON -DCUDA_ARCH_BIN='7.2,8.7' -DCUDA_ARCH_PTX="" -DBUILD_opencv_python3=ON -D OPENCV_GENERATE_PKGCONFIG=ON-D WITH_GSTREAMER=ON -D WITH_LIBV4L=ON -D BUILD_TESTS=OFF -D BUILD_PERF_TESTS=OFF -D BUILD_EXAMPLES=OFF -D CMAKE_BUILD_TYPE=RELEASE"
export ENABLE_EXTRAS=1
pip wheel . --verbose
export ENABLE_CONTRIB=1
pip wheel . --verbose
export ENABLE_HEADLESS=1
pip wheel . --verbose
pip install opencv_*.whl
cd ..

# build from src
pip install -U pydantic_core --no-binary pydantic_core
pip install -U pydantic --no-binary pydantic
pip install -U simsimd  --no-binary simsimd
pip install -U albucore --no-binary albucore
pip install -U albumentations --no-binary albumentations

# others
pip install psycopg2-binary
pip install lapx
pip install shapely
pip install scikit-learn
pip install tqdm
pip install shapely
pip install pympler
pip install onnxruntime
pip install ultralytics
