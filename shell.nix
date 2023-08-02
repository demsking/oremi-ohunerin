{ pkgs ? import <nixpkgs> {} }:

let
  envDir = "$(pwd)/venv";
in

pkgs.mkShell {
  nativeBuildInputs = [
    # devtools
    pkgs.tmux
    pkgs.ruff
    pkgs.gitmux
    pkgs.poetry
    pkgs.gnumake
    pkgs.checkmake
    pkgs.pre-commit
    pkgs.docker-compose
    pkgs.tmuxinator
    pkgs.python310
    pkgs.python310Packages.pip
    pkgs.python310Packages.wheel
    pkgs.python310Packages.build
    pkgs.python310Packages.twine
    pkgs.python310Packages.virtualenv
    pkgs.python310Packages.pre-commit-hooks
    pkgs.stdenv.cc.cc.lib

    # dependencies for the test client
    pkgs.portaudio

    # CUDA
    pkgs.cudatoolkit
    pkgs.cudaPackages.cuda_cudart
    pkgs.cudaPackages.cudnn
    pkgs.cudaPackages.cuda_cupti
    pkgs.cudaPackages.nccl
    pkgs.cudaPackages.tensorrt
    pkgs.linuxPackages.nvidia_x11
  ];
  shellHook = ''
    # CUDA
    export PATH="${pkgs.cudatoolkit}/bin:$PATH"
    export EXTRA_CCFLAGS="-I/usr/include"
    export EXTRA_LDFLAGS="-L/lib -L${pkgs.linuxPackages.nvidia_x11}/lib"
    export LD_LIBRARY_PATH=${pkgs.cudatoolkit}/target-linux-x64:$LD_LIBRARY_PATH
    export LD_LIBRARY_PATH=${pkgs.cudatoolkit}/lib:$LD_LIBRARY_PATH
    export LD_LIBRARY_PATH=${pkgs.cudaPackages.cuda_cudart}/lib:$LD_LIBRARY_PATH
    export LD_LIBRARY_PATH=${pkgs.cudaPackages.cudnn}/lib:$LD_LIBRARY_PATH
    export LD_LIBRARY_PATH=${pkgs.cudaPackages.cuda_cupti}/lib:$LD_LIBRARY_PATH
    export LD_LIBRARY_PATH=${pkgs.cudaPackages.nccl}/lib:$LD_LIBRARY_PATH
    export LD_LIBRARY_PATH=${pkgs.cudaPackages.tensorrt}/lib:$LD_LIBRARY_PATH
    export LD_LIBRARY_PATH=${pkgs.linuxPackages.nvidia_x11}/lib:$LD_LIBRARY_PATH
    export LD_LIBRARY_PATH=${pkgs.linuxPackages.nvidia_x11}/host-linux-x64:$LD_LIBRARY_PATH

    # Python
    export PATH="${pkgs.ruff}/bin:$PATH"
    export LD_LIBRARY_PATH=${envDir}/lib:$LD_LIBRARY_PATH
    export LD_LIBRARY_PATH=${pkgs.portaudio}/lib:$LD_LIBRARY_PATH
    export LD_LIBRARY_PATH=${pkgs.stdenv.cc.cc.lib}/lib:$LD_LIBRARY_PATH
    export PIP_PREFIX=${envDir}
    export PYTHONUSERBASE=${envDir}
    export PYTHON_SITE_PACKAGES=$PIP_PREFIX/${pkgs.python310.sitePackages}:$(pwd)
    export PYTHONPATH="$PYTHON_SITE_PACKAGES:$PYTHONPATH"

    if $isLinux; then
      export PORTAUDIO_LIBNAME=libportaudio.so
      git apply sounddevice.py.patch
    fi

    virtualenv `basename ${envDir}`
    source ${envDir}/bin/activate
  '';
}
