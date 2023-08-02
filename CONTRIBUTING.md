# Contributing to Oremi Sound Detector Server

## Before Submitting an Issue

Check that [our issue database](https://gitlab.com/demsking/oremi-sds/issues)
doesn't already include that problem or suggestion before submitting an issue.
If you find a match, you can use the "subscribe" button to get notified on
updates. Do *not* leave random "+1" or "I have this too" comments, as they
only clutter the discussion, and don't help resolving it. However, if you
have ways to reproduce the issue or have additional information that may help
resolving the issue, please leave a comment.

## Writing Good Bug Reports and Feature Requests

Please file a single issue per problem and feature request. Do not file combo
issues. Please do not submit multiple comments on a single issue - write your
issue with all the environmental information and reproduction steps so that an
engineer can reproduce it.

The community wants to help you find a solution to your problem, but every
problem is unique. In order for an engineer to help resolve your issue, they
need to be able to reproduce it. We put the product through extensive manual
and automated QA for every release, and verify all of its functionality. Any
feature that was previously working in a release that is no longer working is
marked as a severity/blocker for immediate review.

This means that if you are encountering an error, it is likely due to a unique
configuration of your system. Reproducing your specific error may require
significant information about your system and environment. Help us in advance
by providing a complete assessment of your system and the steps necessary to
reproduce the issue.

Therefore:

* The details of your environment including OS version, Python version.
* Provide reproducible steps, what the result of the steps was, and what you
  would have expected.
* A detailed description of the behavior that you expect.

## Development Setup

1. [Install Nix Package Manager](https://nixos.org/manual/nix/stable/installation/installing-binary.html)

2. [Install `direnv` with your OS package manager](https://direnv.net/docs/installation.html#from-system-packages)

3. [Hook it `direnv` into your shell](https://direnv.net/docs/hook.html)

4. **Allow unfree package on Nix config**

   ```sh
   mkdir -p ~/.config/nixpkgs
   echo '{ allowUnfree = true; }' >> ~/.config/nixpkgs/config.nix
   ```

5. **Install TensorRT**

   To use the TensorRT derivation, you must join the NVIDIA Developer Program and
   download the 8.5.3.1 Linux x86_64 TAR package for CUDA 11.8 from
   https://developer.nvidia.com/nvidia-tensorrt-download.

   Once you have downloaded the file, add it to the store with the following
   command, and try building this derivation again.

   ```sh
   nix-store --add-fixed sha256 TensorRT-8.5.3.1.Linux.x86_64-gnu.cuda-11.8.cudnn8.6.tar.gz
   ```

6. **Install dependencies**

   At the top-level of your project run:

   ```sh
   direnv allow
   ```

   The next time your launch your terminal and enter the top-level of your
   project, `direnv` will check for changes.

7. **Start environment**

   ```sh
   make env
   ```

   This will starts a preconfigured Tmux session.
   Please see the [.tmuxinator.yml](.tmuxinator.yml) file.

**Nvidia setup**

- [How to install the NVIDIA drivers on Ubuntu 21.04](https://linuxconfig.org/how-to-install-the-nvidia-drivers-on-ubuntu-21-04)
- [Install the NVIDIA Container Toolkit](https://docs.nvidia.com/ai-enterprise/deployment-guide-bare-metal/0.1.0/docker.html#enabling-the-docker-repository-and-installing-the-nvidia-container-toolkit)

**Ubuntu Nvidia Setup**

```sh
# Automatically install missing drivers
sudo ubuntu-drivers autoinstall

# Install Nvidia Docker Runtime
sudo apt install nvidia-docker2

# Reboot
sudo reboot
```

> Note: I realized that I couldn't use the Nvidia graphics card after installing
the `nvidia-modprobe` package. But once uninstalled and the system restart
everything was normal again.

**Makefile targets**

| Target            | Description                                                            |
|-------------------|------------------------------------------------------------------------|
| env               | Start the development environment using tmuxinator.                    |
| start             | Start both server and test client.                                     |
| lint              | Run linting checks on the codebase using pre-commit.                   |
| fix               | Automatically fix any linting issues found by ruff.                    |
| test              | Run tests using pytest.                                                |
| coverage          | Generate a coverage report for the codebase using pytest.              |
| coverage-html     | Generate an HTML coverage report for the codebase using pytest.        |
| outdated          | Show outdated dependencies using poetry.                               |
| clean             | Clean up build artifacts and temporary files.                          |
| dist              | Build a distribution of the project using poetry and twine.            |
| publish           | Publish a distribution of the project to TestPyPI using twine.         |
| update-locale     | Update locale files for the Flutter app.                               |
| update-snapshots  | Update snapshots for tests using pytest.                               |


Please see the [Makefile](Makefile) for the full list of targets.

## Documentation

**PocketSphinx**

- [Building a phonetic dictionary](https://cmusphinx.github.io/wiki/tutorialdict)

**GPU Documentations**

- [How to install the NVIDIA drivers on Ubuntu 21.04](https://linuxconfig.org/how-to-install-the-nvidia-drivers-on-ubuntu-21-04)
- [Installing CUDA, tensorflow, torch for R & Python on Ubuntu 20.04](https://heads0rtai1s.github.io/2021/02/25/gpu-setup-r-python-ubuntu/)
- [NixOS supports using NVIDIA GPUs](https://nixos.wiki/wiki/CUDA)
- [KDE Plasma/Wayland/Nvidia](https://community.kde.org/Plasma/Wayland/Nvidia)
- [Install the NVIDIA Container Toolkit](https://docs.nvidia.com/ai-enterprise/deployment-guide-bare-metal/0.1.0/docker.html#enabling-the-docker-repository-and-installing-the-nvidia-container-toolkit)

## Contribute

Contributions to Oremi Sound Detector Server are welcome. Here is how you can
contribute:

1. [Submit bugs or a feature request](https://gitlab.com/demsking/oremi-sds/issues)
   and help us verify fixes as they are checked in
2. Create your working branch from the `dev` branch:
   `git checkout dev -b feature/my-awesome-feature`
3. Write code for a bug fix or for your new awesome feature
4. Write test cases for your changes
5. [Submit merge requests](https://gitlab.com/demsking/oremi-sds/merge_requests)
   for bug fixes and features and discuss existing proposals
