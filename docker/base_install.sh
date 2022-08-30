#!/bin/sh
# install basic tools
export DEBIAN_FRONTEND=noninteractive
apt-get clean
apt-get -y update -y -qq
apt-get -y install -y --no-install-recommends \
        git \
        unzip \
        htop \
        sudo \
        lsb-release \
        libboost-all-dev \
        build-essential \
        curl \
        wget \
        ca-certificates \
        software-properties-common \
        apt-transport-https \
        gnupg

# install docker
mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
apt-get -y -qq update
apt-get install -y --no-install-recommends  docker-ce docker-ce-cli containerd.io docker-compose-plugin

usermod -aG docker ubuntu
