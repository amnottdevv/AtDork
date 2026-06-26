# Installation Guide

AtDork requires **Python >= 3.9** and works seamlessly across **Linux (including WSL), macOS, and Windows**.

---

## 1. Installation via PyPI (Recommended)

The most direct and stable method to acquire AtDork is via the Python Package Index:

````bash
pip install atdork
````

## 2. Installing From Source (Development Mode)

If you wish to test bleeding-edge features, inspect the code, or modify internal wordlists, build it locally:

````bash
# Clone the repository
git clone [https://github.com/amnottdevv/atdork.git](https://github.com/amnottdevv/atdork.git)
cd atdork

# Install using editable mode
pip install -e .
````

## 3. Post-Installation Verification

Validate that the CLI entry point successfully mapped to your system`s PATH variables by pulling the current version manifest:

````bash
atdork --version
````

**Expected Output:**

````text
atdork 1.3.8
````

## 4. Optional Dependencies

If you plan to utilize **Tor Integration**, ensure the native Tor service is up and running locally on your system:

````bash
# Debian/Ubuntu / WSL
sudo apt update && sudo apt install tor -y
sudo service tor start

# macOS
brew install tor
brew services start tor
````