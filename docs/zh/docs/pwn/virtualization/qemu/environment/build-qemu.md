# QEMU のダウンロードとビルド

この文書では、ソースコードから QEMU をビルドする方法を紹介します。

## QEMU のソースコードを入手する

[qemu の公式サイト](https://download.qemu.org)から、対応するバージョンのソースコードをダウンロードできます。

```shell
$ wget https://download.qemu.org/qemu-7.0.0.tar.xz
$ tar -xf qemu-7.0.0.tar.xz
```

[GitHub](https://github.com/qemu/qemu) から直接取得することもできます。

```shell
$ git clone git@github.com:qemu/qemu.git
```

## QEMU をビルドする

まず、必要な依存パッケージをインストールします。

```shell
$ sudo apt -y install ninja-build build-essential zlib1g-dev pkg-config libglib2.0-dev binutils-dev libpixman-1-dev libfdt-dev
```

次に、build ディレクトリを作成し、対応するビルドオプションを設定します。

```shell
$ mkdir build && cd build
build$ ../qemu-7.0.0/configure --enable-kvm --target-list=x86_64-softmmu --enable-debug
```

ここでは、次のビルドオプションを手動で指定しています。

- `--enable-kvm`:kvm のサポートを有効にします。
- `--target-list=<アーキテクチャ名>`:ビルドする CPU アーキテクチャを指定します。ここでは `x86_64-softmmu` を指定しており、x86 アーキテクチャの 64 ビット CPU 向けにビルドすることを意味します。
- `--enable-debug`:Qemu をデバッグできるようにします。

あとは、そのまま `make` を実行するだけです。

```shell
build$ make -j$(nproc)
```

ビルドが完了すると、カレントディレクトリに新しい実行ファイル `qemu-system_x86-64` ができています。これが Qemu 本体です。

自分でビルドした QEMU をコマンドラインから起動したい場合は、`make install` コマンドを実行すると、`/bin` ディレクトリに自動的にインストールされます。

```shell
build$ sudo make install
```

## QEMU をデバッグする

QEMU では、`-s` や `-gdb tcp::1234` のような追加パラメータによって、仮想マシンをデバッグできます(たとえば Linux kernel のデバッグ)。しかし、**QEMU 本体を直接デバッグ**したい場合(たとえば自作のエミュレートデバイスのデバッグ)もあり、このときは Host 上の QEMU プロセスをデバッグ対象にする必要があります。

QEMU も本質的にはホスト上で動作する 1 つのプロセスなので、対応する pid を見つけさえすれば、そのまま `gdb attach` でデバッグできます。

## REFERENCE

[【VIRT.0x00】Qemu - I：Qemu 简易食用指南](https://arttnba3.cn/2022/07/15/VIRTUALIZATION-0X00-QEMU-PART-I/)

[QEMU 源码编译](https://hlyani.github.io/notes/openstack/qemu_make.html)
