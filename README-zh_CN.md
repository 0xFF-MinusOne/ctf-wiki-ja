> これは [ctf-wiki/ctf-wiki](https://github.com/ctf-wiki/ctf-wiki) の日本語訳(簡体字中国語から翻訳)です。Pwn・Reverse・Executable の部分だけを訳しています。原著と同じ [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/) で提供します。非営利の目的でのみ利用できます。原文から翻訳(変更)しています。

<div align="center">

<a href="https://ctf-wiki.org/static/img/logo.png" target="_blank"><img src="https://ctf-wiki.org/static/img/logo.png" width="128" height="128"></a>

# CTF Wiki

<p align="center">

Come and join us, we need you!

[![](https://img.shields.io/discord/1115906685450596435?style=for-the-badge&color=%237289DA&label=Discord&logo=discord&logoColor=white")](https://discord.gg/ekv7WDa9pq)  [![](https://img.shields.io/github/stars/CTF-Wiki/CTF-Wiki?style=for-the-badge&color=black&label=Stars&logo=github&logoColor=white")](https://github.com/CTF-Wiki/CTF-Wiki/stargazers)

</p>

</div>

## Introduction

[中文](./README-zh_CN.md)  [English](./README.md)

ようこそ **CTF Wiki** へ。

**CTF**(Capture The Flag、旗取りゲーム)は 1996 年の世界的なハッカーの祭典 **DEFCON** に始まった、セキュリティ愛好家どうしの競技です。

**CTF** は多くの分野にまたがり、内容も雑多です。そのうえセキュリティ技術の進歩はますます速くなり、**CTF** の問題は難しくなる一方で、初心者にとってのハードルは高くなっています。ネット上の資料はたいてい断片的で細かいものばかりなので、初心者は **CTF** に関わる分野の知識をどう体系的に学べばよいか分からず、多くの時間を費やして苦労することが少なくありません。

**CTF** が好きな仲間が **CTF** にもっと入門しやすくなるように、2016 年 10 月に **CTF Wiki** は Github で最初の commit を行いました。内容が充実するにつれて、**CTF Wiki** はますます多くのセキュリティ愛好家に好まれるようになり、会ったこともない仲間が少しずつ参加してくれるようにもなりました。

自由なサイトとして、**CTF** の近年の問題を軸に、**CTF Wiki** は **CTF** の各分野の知識を紹介し、初心者が **CTF** 関連の知識をよりよく学べるようにしています。

現在、**CTF Wiki** には **CTF** の各分野の基礎知識が主に収められており、次の内容の充実に力を入れています。

- CTF 競技での発展的な知識
- CTF 競技での良問

上記の充実させたい内容については、CTF Wiki の [Projects](https://github.com/ctf-wiki/ctf-wiki/projects) を参照してください。取り組み中のことと今後の予定が詳しく挙げられています。

**CTF Wiki** は **CTF** をもとにしていますが、**CTF** に限定されることはありません。今後、**CTF Wiki** は次のことを行います。

- セキュリティ研究で使うツールを紹介する
- 実際のセキュリティの現場とのつながりをより強める

さらに、次の 2 点から、

- 技術はオープンな形で共有されるべきである
- セキュリティの攻防技術は急速に更新されており、新しい防御技術に直面すると、古い攻撃技術はいつ通用しなくなってもおかしくない

**CTF Wiki** が書籍を出版することは決してありません。

最後に、**CTF Wiki** はコミュニティから生まれ、**独立した組織**として、**知識の自由**を掲げています。今後も決して商業化せず、**独立と自由**という性質を保ち続けます。

## How to build？

この文書は現在 [mkdocs](https://github.com/mkdocs/mkdocs) を使い、[https://ctf-wiki.org](https://ctf-wiki.org) に公開されています。

このプロジェクトはそのままローカルにも構築できます。手順は次のとおりです。

```shell
# 1. clone
git clone https://github.com/ctf-wiki/ctf-wiki.git
# 2. requirements
pip install -r requirements.txt
# generate static file in site/
python3 scripts/docs.py build-all
# deploy at http://127.0.0.1:8008
python3 scripts/docs.py serve
```

**mkdocs でローカルに構築したサイトは動的に更新されます。つまり、md ファイルを修正して保存したあとでページを再読み込みすれば、変更が反映されます。**


ローカルで閲覧したいだけで、文書は修正しないのですか。それなら Docker を試してみてください。

```
docker run -d --name=ctf-wiki -p 4100:80 ctfwiki/ctf-wiki
```
そのあと、ブラウザで [http://localhost:4100/](http://localhost:4100/) にアクセスすれば CTF Wiki を読めます。

## How to practice？

まず、オンラインで読みながら基本的なセキュリティの知識を学びます。

次に、CTF Wiki には 2 つの姉妹プロジェクトがあります。

- CTF Wiki で取り上げた問題は [ctf-challenges](https://github.com/ctf-wiki/ctf-challenges) リポジトリにあります。対応する分類から自分で探してください。
- CTF Wiki で取り上げたツールは、随時 [ctf-tools](https://github.com/ctf-wiki/ctf-tools) リポジトリに追加されます。

## How to make CTF Wiki Better？

Wiki の内容をぜひ書いてください。学んだことや得たことをみんなと共有しましょう。あなたの参加をお待ちしています。

**内容を寄稿すると決める前に、必ず [CONTRIBUTING](https://ctf-wiki.org/en/contribute/before-contributing/) を最後まで読んでください**。寄稿の方法が詳しく書かれています。

CTF Wiki を一緒に充実させてくれた仲間のみなさんに、心から感謝します。

<a href="https://github.com/ctf-wiki/ctf-wiki/graphs/contributors"><img src="https://contrib.rocks/image?repo=ctf-wiki/ctf-wiki" /></a>

## What can you get?

- 新しいことを素早く学ぶ力
- これまでと違う考え方
- 問題を解くことを楽しむ心
- おもしろいセキュリティ技術
- 充実して打ち込める時間

Wiki を読む前に、いくつかアドバイスをさせてください。

- [賢い質問の仕方(提问的智慧)](https://github.com/ryanhanwu/How-To-Ask-Questions-The-Smart-Way)を学びましょう
- Google 検索をうまく使うと、自分をより高められます
- 少なくとも 1 つのプログラミング言語(たとえば Python)を身につけましょう
- 手を動かして実践することが何より役に立ちます
- 技術への好奇心と渇望を持ち続け、あきらめずに続けましょう

> 世界は広く、インターネットは世界を小さくします。本物のハッカーは考え、創造するべきです。今は破壊しているのでも創造しているのでも、覚えておいてください。未来において、その主線が創造であればそれでよいのです。 ——by 余弦

セキュリティの世界は狭く、セキュリティの海は深いものです。セキュリティの道の冒険は、**CTF Wiki** から始めてみませんか。

## Copyleft
<a rel="license" href="http://creativecommons.org/licenses/by-nc-sa/4.0/"><img alt="クリエイティブ・コモンズ・ライセンス" style="border-width:0" src="https://i.creativecommons.org/l/by-nc-sa/4.0/88x31.png" /></a><br />この作品は<a rel="license" href="http://creativecommons.org/licenses/by-nc-sa/4.0/">クリエイティブ・コモンズ 表示-非営利-継承 4.0 国際 ライセンス</a>のもとで提供されています。

