## はじめに

現在の CTF の Pwn 問題は、Linux 上のユーザー態 Pwn が中心です。そのため、通常はローカルに Linux の実行環境が必要になります。これは Linux の仮想マシンをインストールすることで用意できます。物理マシンに Linux OS をインストールしてもかまいません。

Linux Pwn 問題のリモート環境は、ほとんどが [Ubuntu](https://ubuntu.com/) です。そのため、ローカルで問題をデバッグしやすくするには、通常、問題のバージョンに合った Ubuntu の実行環境を用意する必要があります。ただし、_これは Ubuntu をメインの OS として使わなければならないという意味ではありません_。好きな別の Linux ディストリビューション(Gentoo、openSUSE、Debian、Fedora、Arch、NixOS など)を使い続け、Docker で対応する Ubuntu の問題用環境を作ることもできます。

従来の CTF Pwn 問題は、通常次のツールだけで解けます。

- IDA:問題の逆解析に使います。
- Python + pwntools:エクスプロイトスクリプトの作成に使います。
- gdb + pwndbg/peda:問題のバイナリのデバッグに使います。

なお、初心者のうちは、pwntools の上に過度に二次ラップしたパッケージは推奨しません。エクスプロイトスクリプトで lambda 式を使って過度に簡略化することも推奨しません。ある程度学んでから、個人の使い方に合わせて決めることをお勧めします。

また、一部の問題では追加の環境が必要になることがあります(たとえば kernel pwn には qemu が必要です)。それらについては、対応する問題を扱うときに個別に説明します。

## Docker で CTF Pwn の問題用環境を構築する(推奨)

エクスプロイトスクリプトが確実に通るようにするには、通常、同じ実行環境をローカルに用意し、リモートで攻撃する前にローカルでテストする必要があります。しかし CTF のリモート環境は多種多様で、環境ごとに別々の Ubuntu 仮想マシンを用意すると、各仮想マシンにデバッグ環境を一式構築しなければならず、大量のディスク容量も使います。さらに、ローカル環境とリモート環境のマイナーバージョンが一致する保証もありません。マイナーバージョンごとに仮想マシンを作ってアップグレードしない、というなら別ですが、この解決策はスマートではありません。

`LD_PRELOAD` 引数でプログラムの実行前に libc をあらかじめロードするのは、ある程度は現実的な解決策です。libc のメジャーバージョンが同じなら、異なるマイナーバージョンをロードしても通常は問題ありません。しかし、システム環境によって ld のバージョンが異なるため、ld のバージョンをまたいで異なるバージョンの libc をロードすると segmentation fault が起き、問題を正常に実行・デバッグできなくなることがあります。

Linux のユーザー環境は、Windows のように強いバイナリの前方互換性を持っているわけではありません。しかしユーザー環境はカーネル環境に依存しており、カーネルがユーザー態に公開するインターフェース、つまりシステムコールに依存しています。これは簡単に変更されたり互換性が壊されたりするものではありません。そのため、対応する新しいユーザー環境を別に用意する方法、つまり Docker のような OS レイヤーの仮想化方式を使えば、さまざまな Pwn 問題に対応した元の環境を非常に簡単に構築できます。

### Docker 環境の構築

Docker のインストールは、使っている Linux ディストリビューションに応じて、[Docker 公式サイト](https://docs.docker.com/engine/install/)またはディストリビューション自身の Wiki を参照して設定してください。ここでは詳しく述べません。

### Docker イメージの作成

次の Dockerfile で作成するイメージをテンプレートとします。必要に応じて自由に変更してください。

```dockerfile
FROM ubuntu:24.04

ARG DEBIAN_FRONTEND=noninteractive

# pre-install softwares
RUN sed -i "s/http:\/\/archive.ubuntu.com/http:\/\/mirrors.tuna.tsinghua.edu.cn/g" /etc/apt/sources.list
RUN dpkg --add-architecture i386
RUN apt-get -y update && apt-get upgrade -y
RUN apt-get install -y lib32z1 apt-transport-https \
    python3 python3-pip python3-venv python3-poetry python3-dev python3-setuptools \
    libglib2.0-dev libfdt-dev libpixman-1-dev zlib1g-dev libc6-dbg libc6-dbg:i386 libgcc-s1:i386 \
    vim nano netcat-openbsd openssh-server git unzip curl tmux konsole wget sudo \
    bison flex build-essential gcc-multilib \
    qemu-system-x86 qemu-user qemu-user-binfmt \
    gcc gdb gdbserver gdb-multiarch clang lldb make cmake

# enable ssh login
RUN rm -f /etc/service/sshd/down
RUN sed -ri 's/^#?PermitRootLogin\s+.*/PermitRootLogin yes/' /etc/ssh/sshd_config &&\
    sed -ri 's/#UseDNS\ no/UseDNS\ no/g' /etc/ssh/sshd_config && \
    sed -ri "s/StrictModes yes/StrictModes no/g" /etc/ssh/sshd_config && \
    sed -ri "s/UsePAM yes/UsePAM no/g" /etc/ssh/sshd_config

# enable login with password
RUN echo 'PasswordAuthentication yes' >> /etc/ssh/sshd_config

# defaultly we have a user `ubuntu` in the image
RUN echo "ubuntu:123456" | chpasswd && \
    echo "root:123456" | chpasswd

# add sudo
RUN usermod -aG sudo ubuntu

# enable ssh key login
#RUN mkdir /home/ubuntu/.ssh && \
#    echo "Your ssh key" > /home/ubuntu/.ssh/authorized_keys

# keep container running
RUN echo "#!/bin/sh\nservice ssh restart\nsleep infinity" > /root/start.sh
RUN chmod +x /root/start.sh

# create venv for pip
RUN python3 -m venv /pip_venv && \
    chown -R ubuntu:ubuntu /pip_venv && \
    echo "\n\n# pip venv\nsource /pip_venv/bin/activate" >> /home/ubuntu/.bashrc

# pwn-related tools
RUN /pip_venv/bin/pip config set global.index-url http://pypi.tuna.tsinghua.edu.cn/simple && \
    /pip_venv/bin/pip config set global.trusted-host pypi.tuna.tsinghua.edu.cn && \
    /pip_venv/bin/pip install -U pip && \
    /pip_venv/bin/pip install --no-cache-dir \
    pwntools \
    ropgadget \
    z3-solver \
    smmap2 \
    apscheduler \
    ropper \
    unicorn \
    keystone-engine \
    capstone \
    angr \
    pebble \
    r2pipe \
    LibcSearcher \
    poetry

RUN git clone https://github.com/pwndbg/pwndbg && \
    cd pwndbg && chmod +x setup.sh && ./setup.sh

CMD ["/root/start.sh"]

EXPOSE 22

```

空のフォルダに `Dockerfile` という名前のファイルを作成して上記の内容を書き込み、次のコマンドを実行します。

```shell
$ docker build -t pwnenv_ubuntu24 .
```

> 注:ネットワークの事情でイメージのビルドを完了できない場合は、イメージのビルドにプロキシを設定できます。通常は Dockerfile に次の内容を追加するだけです。
> 
> ```dockerfile
> ENV HTTP_PROXY=http://your-proxy:port
> ENV HTTPS_PROXY=http://your-proxy:port
> ```
> 
> プロキシサーバーがローカルにある場合は、ローカルネットワークを使ってビルドすることもできます。
> 
> ```shell
> docker build --network="host" -t pwnenv_ubuntu24 .
> ```

これで、`pwnenv_ubuntu24` という名前の、問題用環境入りの Ubuntu24 イメージができました。`docker images` コマンドで確認できます。

```shell
$ docker images                                              
REPOSITORY                                       TAG       IMAGE ID       CREATED             SIZE
pwnenv_ubuntu24                                  latest    64f87a598f87   2 hours ago    3.6GB
```

先頭行のベースイメージを変更すれば、別の Ubuntu ディストリビューションをベースにした docker イメージも作成できます。

### Docker イメージからコンテナを作成する

次のコマンドを実行するだけで、いま作成した Docker イメージをもとに新しいコンテナを作成できます。便宜上、スクリプトにしておくとよいでしょう。各引数の説明は次のとおりです。

- `-d`:コンテナをバックグラウンドで実行する
- `-p 25000:22`:コンテナの `22` 番ポートをローカルの `25000` 番ポートにマッピングする
- `--name=pwn24`:コンテナ名を `pwn24` にする
- `-v ~/Desktop/CTF:/CTF`:ローカルの `~/Desktop/CTF` ディレクトリをコンテナ内の `/CTF` ディレクトリにマッピングする。これでコンテナ内からローカルのファイルにアクセスでき、ファイルをコンテナに何度もコピーする必要がありません
- `pwnenv_ubuntu24`:コンテナの作成に使うイメージ

```shell
$ docker run \
	-d \
	-p 25000:22 \
	--name=pwn24 \
	-v ~/Desktop/CTF:/CTF \
	pwnenv_ubuntu24
```

そのあと、次のコマンドでコンテナに入れます。

```shell
$ docker exec -w /CTF \
        -e TERM=xterm-256color \
        -u ubuntu \
        -it pwn24 \
        bash
```

ローカルのディレクトリをコンテナと直接共有せず、必要なファイルをコンテナにコピーしたい場合は、docker cp コマンドを使えます。

```shell
$ docker cp 本地源文件路径 容器名:容器内目的路径
$ docker cp 容器名:容器内源文件路径 本地目的路径
```

コンテナには ssh サービスを設定してあるので、ssh でコンテナ環境に接続することもできます。これにより vscode などのツールでコンテナ内部に接続できます。

```shell
$ ssh root@localhost -p 25000
```

コンテナ環境をいじって壊してしまった場合は、`docker rm コンテナ名` でそのまま削除し、あらためて `docker run` で新しいコンテナを作成すれば済みます。なお、この方法では、コンテナに新しくコピーしたファイルは削除されます(マウントしたディレクトリは削除されません)。

### Docker コンテナをローカルのグラフィカルインターフェースに接続する

pwntools に付属のデバッグコマンド `gdb.attach()` は新しいウィンドウを作成する必要があり、コンテナ内でそのまま実行すると失敗します。そのため、コンテナをローカルのグラフィックサービスに接続し、ネイティブな動作(新しいウィンドウが直接開く)を実現する必要があります。

> この方法が面倒な場合は、tmux でマルチウィンドウを設定することもできます。`gdb.attach()` コマンドを実行する前に `context.terminal = ['tmux', 'splitw', '-h']` を実行するだけです。

#### For Wayland

Wayland 環境では、コンテナ作成時に追加の引数を付ける必要があります。

```shell
$ docker run \
	-d \
	-p "25000:22" \
	--name=pwn24 \
	-v ~/Desktop/CTF:/CTF \
	-e XDG_RUNTIME_DIR=/tmp \
	-e DISPLAY=$DISPLAY \
	-e WAYLAND_DISPLAY=$WAYLAND_DISPLAY \
	-v $XDG_RUNTIME_DIR/$WAYLAND_DISPLAY:/tmp/$WAYLAND_DISPLAY \
	-e QT_QPA_PLATFORM=wayland \
	pwnenv_ubuntu24
```

そのあと、`gdb.attach()` を実行する前に、次の python 文のいずれかを実行して設定します。使っているデスクトップ環境に合わせて選んでください。

```python
context.terminal = ['konsole', '-e', 'sh', '-c'] # for KDE
context.terminal = ['gnome-terminal', '-e', 'sh', '-c'] # for Gnome
```

#### For X11

X11 のグラフィックサービスを使う場合は、コンテナ作成時に次の引数を付ける必要があります。

```shell
$ docker run \
	-d \
	-p "25000:22" \
	--name=pwn24 \
	-v ~/Desktop/CTF:/CTF \
	-v /tmp/.X11-unix:/tmp/.X11-unix \
	-e DISPLAY=$DISPLAY \
	pwnenv_ubuntu24
```

そのあと、`gdb.attach()` を実行する前に、次の python 文のいずれかを実行して設定します。使っているデスクトップ環境に合わせて選んでください。

```python
context.terminal = ['konsole', '-e', 'sh', '-c'] # for KDE
context.terminal = ['gnome-terminal', '-e', 'sh', '-c'] # for Gnome
```

> [Running pwnlib gdb (pwntools) feature inside Docker](https://gist.github.com/turekt/71f6950bc9f048daaeb69479845b672b) を参照してください。

## ローカルに直接 CTF Pwn の問題用環境を構築する

Docker を使う以外に、ローカルに直接問題用環境を構築することもできます。通常の Linux ユーザー態 pwn 問題では、通常次のソフトウェアだけが必要です。

- IDA:問題の逆解析に使います。
- Python + pwntools:エクスプロイトスクリプトの作成に使います。
- gdb + pwndbg/peda:問題のバイナリのデバッグに使います。

### IDA の入手

IDA Pro(interactive Disassembler Professional)は Hex-Rays 社が提供する対話型の逆アセンブルツールで、ソフトウェアのリバースエンジニアリングで最も普及している静的解析ツールです。IDA Pro を使えば、バイナリプログラムの動作ロジックを簡単に復元でき、そこにある脆弱性の監査もしやすくなります。

[IDA Pro](https://hex-rays.com/ida-pro/) は有償ソフトウェアで、本体と各アーキテクチャのデコンパイルエンジンは別々に課金されます。必要に応じて Hex-rays の公式サイトで該当するソフトウェアライセンスを購入して使ってください。

> 2024 年 4 月時点で、IDA Pro 本体のライセンス価格は 1975 USD、任意の命令セットアーキテクチャのデコンパイル機能のライセンス価格は 2765 USD です。

また、Hex-rays 社はクラウドエンジンベースの無料の逆解析ツール [IDA Free](https://hex-rays.com/ida-free/) も提供しています。現在は x86 の逆解析のみ対応していますが、CTF の Linux ユーザー態 Pwn 問題のほとんどでは通常これで十分です。

### Python のインストール

現在、ほとんどの Linux ディストリビューションには Python の実行環境が標準で付属しているので、通常は Python を手動でインストールする必要はありません。お使いのコンピュータに Python の実行環境がない場合は、使っているディストリビューションに応じてパッケージマネージャで手動インストールしてください。

なお、一部の Linux ディストリビューションでは Python のデフォルトのバージョンが Python2 なので、Python3 を明示的に指定してインストールする必要があるかもしれません。

### venv の python 環境の設定(任意)

一部の Linux ディストリビューション(`openSUSE Tumbleweed` など)で `pip` コマンドを使うと、次のようなエラーが出ることがあります。これはディストリビューション自身のセキュリティポリシーによる制限のためです。

```
error: externally-managed-environment

× This environment is externally managed
╰─> To install Python packages system-wide, try
    zypper install python311-xyz, where xyz is the package
    you are trying to install.
    
    If you wish to install a non-rpm packaged Python package,
    create a virtual environment using python3.11 -m venv path/to/venv.
    Then use path/to/venv/bin/python and path/to/venv/bin/pip.
    
    If you wish to install a non-rpm packaged Python application,
    it may be easiest to use `pipx install xyz`, which will manage a
    virtual environment for you. Install pipx via `zypper install python311-pipx` .

note: If you believe this is a mistake, please contact your Python installation or OS distribution provider. You can override this, at the risk of breaking your Python installation or OS, by passing --break-system-packages.
```

このような場合は、[venv](https://docs.python.org/zh-cn/3/library/venv.html#module-venv) モジュールで「仮想環境」を作成できます。仮想環境は、デフォルトでは他の仮想環境内のソフトウェアや、OS にインストールされた Python インタープリタおよびライブラリから隔離されています。これによりパッケージのインストールの安全性が確保され、環境を簡単に削除して一から作り直せます。

次のコマンドで新しい仮想環境を作成できます(パスが存在しない場合は作成されます)。

```shell
python3 -m venv 自定义的venv文件夹路径
```

作成が終わったら、`source` コマンドで venv に入れます。使っている shell に応じて、いずれか一つを選んでください。

```shell
source 自定义的venv文件夹路径/bin/activate         # for bash
source 自定义的venv文件夹路径/bin/activate.fish    # for fish
source 自定义的venv文件夹路径/bin/activate.csh     # for csh/tcsh
```

> このコマンドを `~/.bashrc` ファイルに追加して、shell を開いたときにデフォルトで実行されるようにすることもできます。

仮想環境は軽量で安全であり、作り直せるという特性があります。そのため、お使いのコンピュータにセキュリティポリシーによる制限がない場合でも、CTF/Pwn 用に独立した Python 仮想環境を作成することをお勧めします。

### pwntools のインストール

[pwntools](https://docs.pwntools.com/en/stable/) は強力な Python パッケージで、基本的な pwn スクリプトの作成環境と、さまざまな便利なエクスプロイトツールを提供します。Python と pip をインストールしたあとは、次のコマンドで簡単にインストールできます。

```shell
python3 -m pip install --upgrade pip
python3 -m pip install --upgrade pwntools
```

そのあと Python では、`from pwn import *` でパッケージ内のさまざまなツールを簡単に使えます。`from pwn import 名前` で必要な特定のツールだけをインポートすることも、`import pwn` でパッケージ名をインポートしてから `pwn.名前` で対応するツールを使うこともできます。

### gdb のインストール

GNU Debugger(GDB)は GNU プロジェクトが開発したソフトウェアデバッガで、gdb を使うとバイナリプログラムを簡単に動的デバッグできます。

gdb はほとんどの Linux ディストリビューションに標準でインストールされています。shell で `gdb` コマンドを入力して確認できます(`q` で終了):

```shell
$ gdb
GNU gdb (GDB; SUSE Linux Enterprise 15) 13.2
Copyright (C) 2023 Free Software Foundation, Inc.
License GPLv3+: GNU GPL version 3 or later <http://gnu.org/licenses/gpl.html>
This is free software: you are free to change and redistribute it.
There is NO WARRANTY, to the extent permitted by law.
Type "show copying" and "show warranty" for details.
This GDB was configured as "x86_64-suse-linux".
Type "show configuration" for configuration details.
For bug reporting instructions, please see:
<http://bugs.opensuse.org/>.
Find the GDB manual and other documentation resources online at:
    <http://www.gnu.org/software/gdb/documentation/>.

For help, type "help".
Type "apropos word" to search for commands related to "word".
(gdb) 
```

お使いのコンピュータに gdb がインストールされていない場合は、次のコマンドでインストールできます。使っているディストリビューションに合わせて選んでください。

Debian / Ubuntu:

```shell
sudo apt-get install -y gdb
```

openSUSE Leap / Tumbleweed / SLE:

```shell
sudo zypper install gdb
```

Arch Linux / Manjaro / EndeavourOS:

```shell
sudo yay -S gdb # AUR を設定していない場合は pacman -S gdb でもインストールできます
```

Fedora / CentOS / RHEL:

```shell
sudo yum install gdb # 実際には yum は dnf へのシンボリックリンクです
```

### pwndbg のインストール

[pwndbg](https://github.com/pwndbg/pwndbg) (/paʊnˈdiˌbʌɡ/) は強力な GDB プラグインで、デバッグ時に実行環境やヒープメモリのレイアウトなどの情報を簡単に確認できます。

pwndbg プロジェクトにはインストールスクリプトが付属しているので、ソースから簡単にインストールできます。

```shell
git clone https://github.com/pwndbg/pwndbg
cd pwndbg
./setup.sh
```

nix パッケージマネージャを使うディストリビューション(NixOS など)では、次のコマンドでインストールできます。

```shell
nix shell github:pwndbg/pwndbg
pwndbg ./your-binary
```

### peda のインストール

> 注:peda と pwndbg はどちらか一方だけをインストールすれば十分です。機能が重複しており、プラグインの競合を避けるためにも、両方のインストールは推奨しません。

[peda](https://github.com/longld/peda) は強力な GDB プラグインで、デバッグ時に実行環境やヒープメモリのレイアウトなどの情報を簡単に確認できます。

peda プラグインは多くの設定を必要としません。ソースコードをローカルにダウンロードしたあと、gdb の設定を更新するだけです。

```shell
git clone https://github.com/longld/peda.git ~/peda
echo "source ~/peda/peda.py" >> ~/.gdbinit
echo "DONE! debug your program with gdb and enjoy"
```
