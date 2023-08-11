{
  description = "Oremi SDS";
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/23.05";
    flake-utils.url = "github:numtide/flake-utils";
  };
  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        envDir = "$(pwd)/venv";
        isLinux = pkgs.lib.system == "linux";
        pkgs = import nixpkgs {
          inherit system;
          config = {
            allowUnfree = true;
          };
        };
        buildToolsVersion = "30.0.3";
      in
      {
        devShell =
          with pkgs; mkShell rec {
            buildInputs = [
              # devtools
              git
              tmux
              ruff
              hadolint
              gitmux
              which
              nodejs
              poetry
              gnumake
              checkmake
              check-jsonschema
              pre-commit
              docker-compose
              tmuxinator
              python310Packages.build
              python310Packages.twine
              python310Packages.virtualenv
              python310Packages.pre-commit-hooks

              # Tensorflow Lite
              cmake
              libusb1
              stdenv.cc.cc.lib

              # dependencies for the test client
              portaudio
            ];
            shellHook = ''
              # Tensorflow Lite
              export PATH="${cmake}/bin:$PATH"
              export NIXPKGS_ALLOW_INSECURE=1

              # Python
              export PATH="${ruff}/bin:$PATH"
              export PATH="${hadolint}/bin:$PATH"
              export LD_LIBRARY_PATH=${envDir}/lib:$LD_LIBRARY_PATH
              export LD_LIBRARY_PATH=${portaudio}/lib:$LD_LIBRARY_PATH
              export LD_LIBRARY_PATH=${libusb1}/lib:$LD_LIBRARY_PATH
              export LD_LIBRARY_PATH=${stdenv.cc.cc.lib}/lib:$LD_LIBRARY_PATH
              export PIP_PREFIX=${envDir}
              export PYTHONUSERBASE=${envDir}
              export PYTHON_SITE_PACKAGES=$PIP_PREFIX/${python310.sitePackages}:$(pwd)
              export PYTHONPATH=$(pwd):$PYTHON_SITE_PACKAGES:$PYTHONPATH

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
            EDITOR = "vim";
            COMPOSE_PROJECT = "oremi-sds";
          };
      });
}
