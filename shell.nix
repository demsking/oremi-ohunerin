{ pkgs ? import <nixpkgs> {} }:

let
  envDir = "$(pwd)/venv";
in

pkgs.mkShell {
  nativeBuildInputs = [
    # devtools
    pkgs.git
    pkgs.tmux
    pkgs.ruff
    pkgs.gitmux
    pkgs.which
    pkgs.nodejs
    pkgs.poetry
    pkgs.gnumake
    pkgs.checkmake
    pkgs.check-jsonschema
    pkgs.pre-commit
    pkgs.docker-compose
    pkgs.tmuxinator
    pkgs.python310
    pkgs.python310Packages.wheel
    pkgs.python310Packages.build
    pkgs.python310Packages.twine
    pkgs.python310Packages.virtualenv
    pkgs.python310Packages.pre-commit-hooks

    # main dependencies
    pkgs.libusb1
    pkgs.stdenv.cc.cc.lib

    # dependencies for the test client
    pkgs.portaudio
  ];
  shellHook = ''
    # Python
    export PATH="${pkgs.ruff}/bin:$PATH"
    export LD_LIBRARY_PATH=${envDir}/lib:$LD_LIBRARY_PATH
    export LD_LIBRARY_PATH=${pkgs.portaudio}/lib:$LD_LIBRARY_PATH
    export LD_LIBRARY_PATH=${pkgs.libusb1}/lib:$LD_LIBRARY_PATH
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

    # Node.js
    mkdir -p .nix-node
    export NODE_PATH=$PWD/.nix-node
    export PATH=$NODE_PATH/bin:$PATH
    npm config set prefix $NODE_PATH

    if ! which gimtoc &> /dev/null; then
      npm install -g gimtoc
    fi

    # Install pre-commit hooks
    pre-commit install -f
  '';
}
