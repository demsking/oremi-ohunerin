{
  description = "Oremi SDS";
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/23.05";
    flake-utils.url = "github:numtide/flake-utils";
  };
  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        envDir = "./venv";
        pkgs = import nixpkgs {
          inherit system;
          config = {
            allowUnfree = true;
          };
        };
        buildToolsVersion = "30.0.3";
      in
      {
        devShells.default = with pkgs; mkShell rec {
          EDITOR = "vim";
          COMPOSE_PROJECT = "oremi-sds";
          PYTHONPATH = "./clients/python:$PYTHONPATH";
          LD_LIBRARY_PATH = "${libusb1}/lib:${stdenv.cc.cc.lib}/lib:$LD_LIBRARY_PATH";
          buildInputs = [
            # tmux
            git
            tmux
            gitmux
            tmuxinator

            # devtools
            docker-compose
            python311
            python311Packages.pip
            python311Packages.wheel
            python311Packages.twine
            python311Packages.toml
            python311Packages.virtualenv
            stdenv.cc.cc.lib

            # certificates
            openssl

            # pre-commit
            ruff
            which
            nodejs
            hadolint
            check-jsonschema
            gnumake
            bandit
            skjold
            shellcheck
            prospector
            pyupgrade
            pre-commit
            editorconfig-checker
            python311Packages.doc8
            python311Packages.pyroma
            python311Packages.autopep8
            python311Packages.pre-commit-hooks
            python311Packages.reorder-python-imports

            # dependencies for client.py
            python311Packages.scipy

            # Tensorflow Lite
            cmake
            libusb1
            stdenv.cc.cc.lib
          ];
          shellHook = ''
            # Python
            export LD_LIBRARY_PATH=${envDir}/lib:$LD_LIBRARY_PATH
            export LD_LIBRARY_PATH=${portaudio}/lib:$LD_LIBRARY_PATH
            export PIP_PREFIX=${envDir}
            export PYTHONUSERBASE=${envDir}
            export PYTHON_SITE_PACKAGES=$PIP_PREFIX/${python311.sitePackages}
            export PYTHONPATH=$(pwd):$PYTHON_SITE_PACKAGES:$PYTHONPATH

            virtualenv `basename ${envDir}`
            VIRTUAL_ENV_DISABLE_PROMPT=true source ${envDir}/bin/activate

            # Node.js
            mkdir -p .nix-node
            export NODE_PATH=$PWD/.nix-node
            export PATH=$NODE_PATH/bin:$PATH,
            npm config set prefix $NODE_PATH

            if ! which gimtoc &> /dev/null; then
              npm install -g gimtoc
            fi

            # Install pre-commit hooks
            pre-commit install -f > /dev/null
          '';
        };
    });
}
