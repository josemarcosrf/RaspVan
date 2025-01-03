# RaspVan (codename: `Fiona`)

Domotics using a Raspberry Pi 3B for our own-built campervan.

At the moment it is _just a simple prototype_ aiming to become a
complete domotic voice-controled system.

Commands can be executed either by _voice_ or by sending _HTTP requests_ to a server.

----

## Table of Contents

<!--ts-->
* [RaspVan (codename: Fiona)](#raspvan-codename-fiona)
  * [Table of Contents](#table-of-contents)
  * [Requirements](#requirements)
  * [Structure](#structure)
    * [Hotword](#hotword)
    * [ASR](#asr)
    * [NLU](#nlu)
    * [Respeaker](#respeaker)
    * [Raspvan](#raspvan)
      * [Relays](#relays)
      * [Bluetoth](#bluetoth)
  * [How to](#how-to)
    * [Installation](#installation)
    * [Finding the sound input device ID](#finding-the-sound-input-device-id)
    * [WiFi and automatic hotspot](#wifi-and-automatic-hotspot)
    * [Wiring and Connections](#wiring-and-connections)
  * [Misc](#misc)

<!-- Added by: jose, at: vie 24 mar 2023 22:54:27 CET -->

<!--te-->
----

## Requirements

Apart from any other requirement defined in the root or any of the sub-modules we
need the following system-wide dependencies:

* [Raspbian Buster](https://www.raspberrypi.org/downloads/raspbian/)
   ([installation guide](https://www.raspberrypi.org/documentation/installation/installing-images/README.md))
* python >= 3.7
* Docker & Docker-compose

## Structure

This repo is organized in a series of sub-modules plus the main solution code under [raspvan](raspvan/]).

To understand how to train, configure, test and run each sub-module please refer to
the individual readme files.

```bash
# tree -L 1
.
├── asr                     # ASR component (uses vosk-kaldi)
├── assets
├── common
├── config
├── data
├── docker-compose.yml
├── hotword                 # HotWord detection (uses Mycroft/Precise)
├── nlu                     # NLU (sklearn and spacy custom implementation)
├── raspvan                 # client and server systems
├── README.md
├── requirements-dev.txt
├── requirements.txt
├── respeaker
├── scripts
├── setup.cfg
└──  tasks.py               # invoke commands
```

All the `raspvan.workers` communicate through `AMQP` using `rabbitMQ`.
To run the broker backbone glueing all together:

```bash
docker-compose up -d rabbit
```

### Hotword

The hotword detection sub-module is based on a custom for of [mycroft/precise](https://github.com/josemarcosrf/mycroft-precise.

To run the rabbitMQ-publisher hot-word worker:

```bash
source .env
source .venv/bin/activate
inv run-hot-word
```

### ASR

The ASR sub-module uses a custom dockerized PyVosk server build for the RaspberryPi:
[jmrf/pyvosk-rpi](https://github.com/josemarcosrf/pyvosk-rpi).

This server listens via websocket to a `sounddevice` stream and performs STT on the fly.

> 💡 For a complete list of compatible models check:
> [vosk/models](https://alphacephei.com/vosk/models)


To try the ASR client & server:
```bash
# Run the dockerized server
docker-compose up asr-server
# ASR from a audio wav file
python -m  asr client -v 2 -f <name-of-the-16kHz-wav-file>
# Or ASR listening from the microphone
python -m  asr client -v 2 -d <microphone-ID>
```

To run the rabbitMQ-triggered ASR worker:

```bash
source .env
source .venv/bin/activate
inv run-asr
```

### NLU

> ⚠️ While the rest of the components use `numpy~=1.16` the NLU components requires
> a newer version in order to work with `scikit`.
>
> The best thing if running locally is to **create a separate virtual environment**
>
> See [nlu/README.md](nlu/README.md)

The NLU engine has two parts:

* A Spacy vectorizer + SVM classifier for **intent classification**
* A `Conditional Random Field` (CRF) for **entity extraction**

> 💡 Check the details in this Colab notebook: [simple-NLU.ipynb](https://colab.research.google.com/drive/1q6Ei9SRdD8Pdg65Pvp8porRyFlQXD4w6#scrollTo=mK2GbpHan6k7)
> 💡 It is advices to collect some voice samples and run them through ASR to use
> these as training samples for the NLU component to train it on real data.

To collect voice samples and apply ASR for the NLU, run:

```bash
# discover the audio input device to use and how many input channel are available
python -m scripts.mic_vad_record -l
# Run voice recording
python -m scripts.mic_vad_record sample.wav -d 5 -c 4
```

### Respeaker

We use `respeaker 4mic hat` as a microphone and visual-feedback with its LED array.

To run the LED pixel demo:

```bash
python -m respeaker pixels
```

To run a recording:

```bash
python -m respeaker record -t 5 -o output.wav
```

### Raspvan

This is the main module which coordinates all the different components.

#### Relays

i2c relay demo:

```shell
inv run-relays
```

#### Bluetoth

To run the bluetooth server:

```shell
inv run-ble-server`
````

<details>

<summary>Setting BLE server as a service</summary>

Create `/etc/systemd/system/ble_server.service` with the following content:

```ini
[Unit]
Description=RaspVan BLE Server + Redis container
Requires=docker.service
After=docker.service

[Service]
Restart=always
ExecStart=/bin/bash /home/pi/start_ble.sh
ExecStop=

[Install]
WantedBy=default.target
```

> Enable on startup: `sudo systemctl enable ble_server.service`
>
> Start with : `sudo systemctl start ble_server`
>
> Check its status with: `sudo systemctl status ble_server`

</details>

## How to

### Installation

Create a virtual environment

```bash
python3.7 -m venv .venv
source .venv/bin/activate
```

And install all the python dependencies

```bash
pip install -r requirements.txt
```

### Finding the sound input device ID

First list all audio devices:

```bash
python -m respeaker print-audio-devices
```

You should get a table simlar to this:

```bash
┏━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━┓
┃ Index ┃ Name     ┃ Max Input Channels ┃ Max Output Channels ┃
┡━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━┩
│     0 │ upmix    │                  0 │                   8 │
│     1 │ vdownmix │                  0 │                   6 │
│     2 │ dmix     │                  0 │                   2 │
│     3 │ default  │                128 │                 128 │
└───────┴──────────┴────────────────────┴─────────────────────┘
```

Device with **index 3**, which can handle several input and output channels,
is the one to pass to the `hotword` and `ASR` workers.

> ⚠️ ALSA won't allow for audio devices to be shared,
> i.e.: accessed simultaneously by more than one application
> when using the sound card directly. ⚠️
>
> Solution: Use the pcm devices, i.e.: plugins. Specifically the dsnoop
> (to have shared input between processes) and dmix (to have several audio outputs on one card).
>
> Copy [config/.asoundrc](config/.asoundrc) to `~./asoundrc`

<details>
  <summary>⚠️ Probably deprecated. Click to expand!</summary>

### WiFi and automatic hotspot

In order to communicate with the RaspberryPi we will configure it to connect to
a series of known WiFi networks when available and to create a Hotspot otherwise.

Refer to [auto-wifi-hotspot](http://www.raspberryconnect.com/network/item/330-raspberry-pi-auto-wifi-hotspot-switch-internet)
from [raspberryconnect/network](http://www.raspberryconnect.com/network).

By default the RaspberryPi will be accessible at the IP: `192.168.50.5` when the hotspot is active.

### Wiring and Connections

TBD

## Misc

* Drawing and simulation tool: [partsim simulator](https://www.partsim.com/simulator)

</details>
