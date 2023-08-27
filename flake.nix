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
        pythonPackages = pkgs.python310Packages;
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
            python310
            python310Packages.pip
            python310Packages.wheel
            python310Packages.twine
            python310Packages.toml
            python310Packages.virtualenv
            stdenv.cc.cc.lib

            # certificates
            openssl

            # pre-commit
            ruff
            which
            nodejs
            hadolint
            check-jsonschema
            gnutar
            gnumake
            pre-commit
            python310Packages.pre-commit-hooks

            # dependencies for client.py
            pythonPackages.scipy
            pythonPackages.sounddevice

            # Tensorflow Lite
            cmake
            libusb1
            stdenv.cc.cc.lib

#             # dependencies for the test client
#             portaudio
          ];
          shellHook = ''
            # Python
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
