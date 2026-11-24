> **これは日本語訳です。**
>
> - 原著: [ctf-wiki/ctf-wiki](https://github.com/ctf-wiki/ctf-wiki)(原著者: ctf-wiki の編集者たち)
> - ライセンス: CC BY-NC-SA 4.0(**非営利の目的でのみ**利用できます) — 翻訳も同じライセンスです([ライセンス全文](LICENSE))。原文から翻訳(変更)しています
> - 訳した範囲: Pwn・Reverse・Executable の説明文と、コード内の原著者のコメント(簡体字中国語から翻訳)
> - 訳していないもの: 暗号・misc・android・blockchain などほかの分野。コードブロック内の図やメモリダンプにある中国語の注釈の一部
> - 日本語サイト: <https://0xff-minusone.github.io/ctf-wiki-ja/>
> - 他の日本語訳: [一覧](https://github.com/orgs/0xFF-MinusOne/repositories?q=-ja)

<div align="center">

<a href="https://ctf-wiki.org/static/img/logo.png" target="_blank"><img src="https://ctf-wiki.org/static/img/logo.png" width="128" height="128"></a>

# CTF Wiki

<p align="center">

ぜひ参加してください。あなたの力が必要です!

[![](https://img.shields.io/discord/1115906685450596435?style=for-the-badge&color=%237289DA&label=Discord&logo=discord&logoColor=white")](https://discord.gg/ekv7WDa9pq)  [![](https://img.shields.io/github/stars/CTF-Wiki/CTF-Wiki?style=for-the-badge&color=black&label=Stars&logo=github&logoColor=white")](https://github.com/CTF-Wiki/CTF-Wiki/stargazers)

</p>

</div>

## はじめに

[中文](./README-zh_CN.md)  [English](./README.md)

**CTF Wiki** へようこそ!

**CTF**(Capture The Flag)は、コンピュータセキュリティ愛好家の競技である **DEFCON CTF** から始まりました。DEFCON CTF は1996年に初めて開催されました。

**CTF** は幅広い分野を扱います。セキュリティ技術の進歩とともに、**CTF** の問題の難易度はどんどん上がっており、その結果、初心者にとって学習の壁は高くなっています。ネット上の情報の多くは散らばっていて、断片的です。初心者は **CTF** を体系的に学ぶ方法が分からないことが多く、それには多くの手間と努力が必要です。

**CTF** に興味のある人が気軽に始められるように、2016年10月に **CTF Wiki** が Github 上で立ち上げられました。内容が少しずつ充実するにつれて、**CTF Wiki** はセキュリティ愛好家から多くの感謝の声をいただきました。その多くは、私たちがおそらく一生会うことはないと思っていた人たちです。

**CTF Wiki** は自由なサイトとして、主に最近の CTF に焦点を当て、**CTF** のあらゆる面の知識と技術を紹介することで、初心者が **CTF** を学びやすくします。

現在、**CTF Wiki** は主に **CTF** の基本的な技術を扱っていますが、次の内容の充実に向けて取り組んでいます。

- CTF で使われる高度な技術
- CTF に登場する特別なトピック

上記の充実させる部分については、計画の詳細が載っている [Projects](https://github.com/ctf-wiki/ctf-wiki/projects) を参照してください。

現在、**CTF Wiki** は主に **CTF** に焦点を当てていますが、**CTF** のトピックだけに厳密に限定されるわけではありません。今後、**CTF Wiki** には次の内容も含まれる予定です。

- セキュリティ研究で使われるツール
- 世の中のセキュリティについてのより多くの議論

加えて、次の2点を踏まえ、

- 技術に関する情報は、オープンに共有されるべきです。
- 新しい技術は常に開発されているため、古い技術は時間とともに廃れていき、新しい技術に置き換えられるべきです。

したがって、**CTF Wiki** が書籍を出版することは決してありません。

最後に、コミュニティから生まれた独立した組織として、**CTF Wiki** は**知識の自由**を掲げ、**商業化されることは決してなく**、常に**独立と自由**という性格を保ちます。

## ビルド方法

CTF Wiki は、内容の表示に [mkdocs](https://github.com/mkdocs/mkdocs) を使っています。そして [https://ctf-wiki.org](https://ctf-wiki.org) に公開されています。

次の手順で、ローカルに構築することもできます。

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

**ローカルの mkdocs は動的に更新されます。たとえば、Markdown ファイルを変更すると、対応するページも変更されます。**

静的に閲覧するだけでよければ、Docker を試してください。

```
docker run -d --name=ctf-wiki -p 4100:80 ctfwiki/ctf-wiki
```
そのうえで [http://localhost:4100/](http://localhost:4100/) にアクセスしてください。

## 練習方法

まず、オンラインで読んで、セキュリティの基礎知識を学びます。

次に、CTF Wiki には2つの姉妹プロジェクトがあります。

- 取り上げた問題はすべて [ctf-challenges](https://github.com/ctf-wiki/ctf-challenges) リポジトリにあり、対応するカテゴリから探せます。
- CTF Wiki で取り上げたツールは、[ctf-tools](https://github.com/ctf-wiki/ctf-tools) リポジトリに随時追加されています。

## CTF Wiki をより良くするには

Wiki の内容を書いて、学んだことを共有していただくことを歓迎します。

**内容を寄稿すると決める前に、[CONTRIBUTING](https://ctf-wiki.org/en/contribute/before-contributing/) を読んでください。**

すでに CTF Wiki に貢献してくださったすべての方に感謝します。

<a href="https://github.com/ctf-wiki/ctf-wiki/graphs/contributors"><img src="https://contrib.rocks/image?repo=ctf-wiki/ctf-wiki" /></a>

## 何が得られるか

- 新しいことを素早く学ぶ力
- 異なる考え方
- 問題を解くことへの愛着
- 面白いセキュリティ技術
- 記憶に残る、充実した経験

Wiki を読む前に、いくつかアドバイスがあります。

- [賢い質問](http://www.catb.org/~esr/faqs/smart-questions.html)のしかたを身につけてください。
- 自分を高めるために、Google 検索を使いこなせるようになってください。
- Python など、少なくとも1つのプログラミング言語に習熟してください。
- 実践は、最も重要な学習手段です。
- 新しい技術を学ぶ情熱と意欲を保ってください。

セキュリティの世界は狭く、探索する領域は広大です。**CTF Wiki** で始めましょう!
