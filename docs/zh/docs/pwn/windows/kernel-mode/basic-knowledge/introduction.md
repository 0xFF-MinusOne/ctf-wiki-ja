# 基礎知識

> オペレーティングシステムの基本理論に詳しくない場合、筆者としては、[オープンソースのモノリシックカーネルである Linux kernel から入門する](https://arttnba3.cn/2021/02/21/OS-0X00-LINUX-KERNEL-PART-I/)ことをむしろおすすめします。この文章では、オペレーティングシステムの基本概念にはほとんど触れません。

Windows オペレーティングシステムの正式名称は**新技術ウィンドウズ**(Windows New Technology、略して **Windows NT**)で、_かつては_**マイクロカーネルアーキテクチャ**(micro kernel)を採用していると称していました。つまり、**大部分のシステムコンポーネントはユーザーモードで存在し、一部の必須コンポーネントだけがカーネルモードで存在する**というものです。しかし実際には、現在の Windows はカーネルモードに多くのものを詰め込んでいるため、現在の NT kernel はむしろ_ハイブリッドカーネル_(hybrid kernel)に近いと言えます。

![Windows カーネルアーキテクチャの全体像](https://s2.loli.net/2025/02/01/o9DzrNqSvLxIfdR.png)

このブログ記事では、主に **64 ビット** Windows NT kernel の基本的な動作原理といくつかの基本コンポーネントを紹介します。主に Windows 10 を例に説明し、_32 ビットに関する内容は扱いません_。

> Windows カーネルのいくつかの構造体の定義は、[このサイト](https://www.vergiliusproject.com/kernels)で参照できます。

## 一、ユーザーモードの部分

Windows NT オペレーティングシステムは、ユーザーモードでは主に次の 4 つの部分に分かれます。

- システムプロセス(System Processes)
- サービス(Services)
- アプリケーション(Applications)
- 環境サブシステム(Environment Subsystem)

Windows のすべてのユーザーモードプログラムは、システムリソースの取得を最終的に `ntdll.dll` が提供するシステムコールインターフェースを通じて行います。

## 二、カーネルモードの部分

NT kernel にはハードウェア的な意味での階層(すべて ring0 で動作する)はありませんが、設計上は階層的な依存関係の考え方があり、図のような 3 つの層に分けられます。

![Windows システムアーキテクチャの階層](https://s2.loli.net/2025/02/01/ZwtEYSgi8UPr7Wx.png)

### 上層:エグゼクティブ(Executive)

**エグゼクティブ**(Executive)は NT kernel の中核部分で、**本質的には従来のオペレーティングシステムのカーネル本体**です。比較的中核となるサブシステムは次のとおりです。

- **オブジェクトマネージャ**(Object Manager):オブジェクトマネージャは**エグゼクティブの下層部分**で、カーネル内では**すべてのリソースがオブジェクト**(object)であり、オブジェクトマネージャがすべてのカーネルオブジェクトの管理を担当します。
- 入出力マネージャ(I/O Manager):ユーザーモードプログラムの I/O 要求(ディスクへのアクセスなど)を受け取り、関連するデバイスへの呼び出しに変換します。
- セキュリティリファレンスモニタ(Security Reference Monitor):Windows は**アクセス制御リスト**(Access Control List)を使ってオブジェクトのセキュリティを判定します。このサブシステムがセキュリティルールの実施を担当します。
- プロセス間通信マネージャ(IPC Manager):異なるプロセス間の通信要求を処理します。
- 仮想メモリマネージャ(Virtual Memory Manager):カーネルレベルでオペレーティングシステム全体のメモリ管理を担当します。
- プロセスマネージャ(Process Manager):プロセスとスレッドの作成と破棄を担当し、_直接のスケジューリングは担当しません_。
- プラグアンドプレイマネージャ(Plug and Play Manager):デバイスの動的なロードとアンロードの際の検出と、対応するサービスの提供を担当します。大部分は実際にはユーザーモードの `Plug and Play` で実装されています。
- 電源マネージャ(Power Manager):電源関連のイベント(シャットダウン、スリープなど)を処理し、関連するドライバに通知します。
- グラフィックデバイスインターフェース(Graphic Device Interface):すべての基本的な描画機能を担当します。NT 4.0 からカーネルモードに移され、動作しています(それ以前はユーザーモードでした)。

エグゼクティブ関連のコードは `ntoskrnl.exe` にあり、ユーザーモードに公開されるインターフェースは `ntdll.dll` にあります。

### 中層:(マイクロ)カーネル(Kernel)

**カーネル**(Kernel)は NT kernel では、マルチプロセッサ間の同期、スレッドの直接スケジューリング、割り込み/例外のディスパッチなど、最も基本的な_ハードウェア側の機能_**だけ**を担当し、「マイクロカーネル」アーキテクチャの基本的な考え方に合致しています。

カーネル関連のコードは `ntoskrnl.exe` にあります。

### 中層:カーネルモードドライバ(Kernel Mode Driver)

Windows のドライバには、ユーザーモードドライバとカーネルモードドライバの 2 種類があります。後者は前者に対応するインターフェースを提供し、データをさらに下層のドライバに渡します。

カーネルモードドライバは図のような 3 つの層に分けられ、下層に近いほど詳細で具体的なハードウェア構造に近くなります。

![](https://s2.loli.net/2025/02/01/KeypmW8xGPViXQH.png)

カーネルモードドライバは独立したモジュール型のコンポーネントとして実装されており、特定の PE ファイルの中にあるわけではありません(LKM に少し似ている?)。

### 下層:ハードウェア抽象化レイヤ(Hardware Abstract Layer)

**ハードウェア抽象化レイヤ**(Hardware Abstract Layer)は、下層のさまざまなハードウェアの細部を隠蔽し、上層のカーネルに**統一された抽象ハードウェアインターフェース**を提供します。たとえば IO インターフェースや割り込みコントローラなどのハードウェアの振る舞いを統一的に抽象化します。

HAL の目的は主にハードウェアアーキテクチャ間の差異をなくすことで、オペレーティングシステムやドライバの開発者が、異なるハードウェアプラットフォーム向けに、具体的なハードウェアアーキテクチャへの依存が小さいコードを書いて、クロスプラットフォームで動かしやすくすることです。これによって、ハードウェアプラットフォームごとに専用のコードを個別に書く必要がなくなります。

HAL が主に担当するのは IO などの汎用リソースの抽象化であり、一部のドライバの一部の操作は、依然として HAL を迂回して直接ハードウェアと通信することに注意してください。

HAL 関連のコードは `hal.dll` にあります。

## 「すべてはオブジェクト」

*NIX 系のシステムにおける「すべてはファイル」という思想と同様に、Windows NT kernel にも**すべてはオブジェクト**(object)であるという考え方があります。ファイル、デバイス、同期機構、レジストリキーなどは**カーネル内ではオブジェクトとして表現され**、各オブジェクトはオブジェクトの基本情報(名前、型、位置など)を格納する `header` と、データを格納する `body` を持ちます。

NT kernel のオブジェクトは 2 種類に分けられます。

- エグゼクティブオブジェクト(Executive Objects):エグゼクティブが外部に公開するリソースオブジェクト(プロセス、スレッド、ファイルなど)で、ユーザーモードから見えます。
- カーネルオブジェクト(Kernel Objects):最も基本的なリソースオブジェクト(物理デバイスなど)で、ユーザーモードから見えません。

### 一、\_OBJECT\_HEADER:オブジェクトの基本情報

NT kernel では、`_OBJECT_HEADER` 構造体がオブジェクトの基本情報を格納します。定義は次のとおりです。
```powershell
kd> dt nt!_OBJECT_HEADER
   +0x000 PointerCount     : Int8B
   +0x008 HandleCount      : Int8B
   +0x008 NextToFree       : Ptr64 Void
   +0x010 Lock             : _EX_PUSH_LOCK
   +0x018 TypeIndex        : UChar
   +0x019 TraceFlags       : UChar
   +0x019 DbgRefTrace      : Pos 0, 1 Bit
   +0x019 DbgTracePermanent : Pos 1, 1 Bit
   +0x01a InfoMask         : UChar
   +0x01b Flags            : UChar
   +0x01b NewObject        : Pos 0, 1 Bit
   +0x01b KernelObject     : Pos 1, 1 Bit
   +0x01b KernelOnlyAccess : Pos 2, 1 Bit
   +0x01b ExclusiveObject  : Pos 3, 1 Bit
   +0x01b PermanentObject  : Pos 4, 1 Bit
   +0x01b DefaultSecurityQuota : Pos 5, 1 Bit
   +0x01b SingleHandleEntry : Pos 6, 1 Bit
   +0x01b DeletedInline    : Pos 7, 1 Bit
   +0x01c Reserved         : Uint4B
   +0x020 ObjectCreateInfo : Ptr64 _OBJECT_CREATE_INFORMATION
   +0x020 QuotaBlockCharged : Ptr64 Void
   +0x028 SecurityDescriptor : Ptr64 Void
   +0x030 Body             : _QUAD
```

オブジェクトには、固定の `_OBJECT_HEADER` のほかに、**追加情報を格納するための optional header を持たせることもでき**、対応する optional header が存在するかは `_OBJECT_HEADER->InfoMask` のマスクで決まります。

![](https://s2.loli.net/2025/02/01/S8hIzlRWCFGjTed.png)

`_OBJECT_HEADER->InfoMask` のマスクに対応するビットが立っている場合、_対応する optional header が存在する_ ことを表します。optional header の格納順序は固定なので、NT kernel は各 header に対応するオフセットを簡単に計算できます。マスクと header の type & size の対応関係は次のとおりです。

| Bit  |              Type              | Size (on X86) |
| :--: | :----------------------------: | :-----------: |
| 0x01 | nt!_OBJECT_HEADER_CREATOR_INFO |     0x10      |
| 0x02 |  nt!_OBJECT_HEADER_NAME_INFO   |     0x10      |
| 0x04 | nt!_OBJECT_HEADER_HANDLE_INFO  |     0x08      |
| 0x08 |  nt!_OBJECT_HEADER_QUOTA_INFO  |     0x10      |
| 0x10 | nt!_OBJECT_HEADER_PROCESS_INFO |     0x08      |

**NT kernel の 19H1 より前のバージョン**では、Windows カーネルは `Pool Allocator` **だけ**を使っており、カーネルプールに確保される各オブジェクトに対して、対応する情報を格納する `_POOL_HEADER` 構造体がありました。

```powershell
kd> dt nt!_POOL_HEADER
   +0x000 PreviousSize     : Pos 0, 8 Bits
   +0x000 PoolIndex        : Pos 8, 8 Bits
   +0x002 BlockSize        : Pos 0, 8 Bits
   +0x002 PoolType         : Pos 8, 8 Bits
   +0x000 Ulong1           : Uint4B
   +0x004 PoolTag          : Uint4B
   +0x008 ProcessBilled    : Ptr64 _EPROCESS
   +0x008 AllocatorBackTraceIndex : Uint2B
   +0x00a PoolTagHash      : Uint2B
```

これにより、カーネルオブジェクトの基本的な構造は次の図のようになります。

![](https://s2.loli.net/2025/02/01/rzoqgZXxNSmsa52.png)

### 二、オブジェクトマネージャと名前空間

NT kernel のすべてのオブジェクトは**オブジェクトマネージャ**(Object Manager)によって管理され、ユーザーモードからのあらゆるオブジェクトへのアクセスは、オブジェクト管理サブシステムを経由する必要があります。オブジェクトマネージャは主に次のタスクを担当します。

- オブジェクトの作成と破棄の管理
- オブジェクト名前空間のデータベースの維持
- プロセスに割り当てられたリソースの追跡
- 特定のオブジェクトに対するアクセス権限の追跡
- オブジェクトのライフサイクルの管理

オブジェクトは異なる[名前空間](https://learn.microsoft.com/zh-cn/windows/win32/termserv/kernel-object-namespaces)(Namespace)に属します。ユーザーセッション(user session)ごとに別の名前空間になり、オブジェクトは作成時にデフォルトで現在のセッションの名前空間に属します。このほかに、グローバルに共有される**グローバル名前空間**もあり、これによってオブジェクトを異なるセッション間で共有できます。

> オブジェクトの作成時に `"Global\"` プレフィックスを付けると、そのオブジェクトをグローバル名前空間に作成できます。たとえば次のコードで、グローバル名前空間に属するイベントオブジェクトを作成できます。
>
> ```cpp
> CreateEvent( NULL, FALSE, FALSE, "Global\\ARTTNBA3" );
> ```
>
> また `"Local\"` プレフィックスによって、オブジェクトをセッション名前空間に作成することを明示することもできます。

### 三、ハンドル(handler)

> Linux のファイルディスクリプタの概念に少し似ていますが、大部分のカーネルオブジェクトに拡張されています。
>
> > 全くわけのわからない訳語で、筆者個人としては _参照子_ と訳したほうがよいと感じます。

**ハンドル**(handler)は、Windows のユーザーモードプログラムが対応するカーネルオブジェクトを管理するために使うオブジェクトディスクリプタで、整数値(32/64 ビットシステムでは 32/64 ビット整数)として表されます。ユーザープログラムは、自分が持つハンドルを通じて、カーネル内の対応するカーネルオブジェクトにアクセスできます。

Windows には、オブジェクト情報を格納するハンドルテーブルが次のように存在します。

- Windows NT kernel のすべてのオブジェクトのハンドルは、グローバルなハンドルテーブルに格納される
- 各プロセスは独自のハンドルテーブルを持つ(そのアドレスはプロセス制御ブロックの `_EPROCESS->_HANDLER_TABLE->TableCode` に格納される)。**プロセスが取得するオブジェクトのハンドル値は、実際には【このテーブルの対応する項目の添字インデックス値 x4】**である(64 ビットシステム、各エントリ 16 バイト)

プロセスのハンドルテーブルの構造は下図のとおりです。第 0 項は予約されており、ハンドルテーブルの項目は `_HANDLE_TABLE_ENTRY` 構造で、その下位 44 ビットの値を 4 ビット左シフトして `0xffff000000000000` を加えたものがオブジェクトヘッダのアドレスです。

> Windows 7 では、プロセスのハンドルテーブルは実際にはオブジェクトのアドレスを単純に格納するだけでしたが、新しいバージョンのカーネルでは、すべてが複雑になっていきました。

![32 ビット NT kernel におけるハンドルテーブルの構造(64 ビットでも原理はほぼ同じ)](https://s2.loli.net/2025/02/01/yZk1NKeIqBcriVS.png)

さらに `TableCode` は下位 4 ビットで**ハンドルテーブルの構造の階層を示します**。つまり、**プロセスのハンドルテーブルは実際には多層構造にでき**、ページテーブルに似ており、**最後の層だけがオブジェクトのアドレスを格納し、それ以外の層はテーブルのアドレスを格納します**。各テーブルのサイズは 4096 バイト(メモリページ 1 枚分)です。

![](https://s2.loli.net/2025/02/01/nU3FkTsiGpPMw8Q.png)

## メモリ管理

メモリ管理はオペレーティングシステムの最も中核的な部分の 1 つであり、味わっておかないわけにはいきません。

### 一、物理メモリ管理

#### カーネルアドレス空間のレイアウト

まず、64 ビット NT kernel のメモリレイアウトの全体図を示します。

> 32 ビットは、Win11 以降はすべて純粋な 64 ビットになったので、ひとまず研究は考えません。

| **Start**               | **End**                   | **Size**  | **Description**          | Usage                                                  |
| ----------------------- | ------------------------- | --------- | ------------------------ | ------------------------------------------------------ |
| FFFF080000000000       | FFFFF67FFFFFFFFF         | 238TB     | Unused System Space      | 使われない領域                                       |
| FFFFF68000000000       | FFFFF6FFFFFFFFFF         | 512GB     | PTE Space                | ページテーブルがある領域                                           |
| FFFFF70000000000       | FFFFF77FFFFFFFFF         | 512GB     | HyperSpace               | 一時的な中継マッピングに使う                                     |
| FFFFF78000000000       | FFFFF78000000FFF         | 4K        | Shared System Page       | 共有メモリ空間。(カーネルのエントリポイント?)各プロセスにマップされている |
| FFFFF78000001000       | FFFFF7FFFFFFFFFF         | 512GB-4K  | System Cache Working Set | システムキャッシュのワーキングセット |
| FFFFF80000000000       | FFFFF87FFFFFFFFF         | 512GB     | Initial Loader Mappings  | 最初のカーネルローダが使う領域                               |
| FFFFF88000000000       | FFFFF89FFFFFFFFF         | 128GB     | Sys PTEs                 | システムページテーブルエントリの領域。MDL でマップされた仮想メモリとドライバイメージはここにある   |
| FFFFF8a000000000       | FFFFF8bFFFFFFFFF         | 128GB     | Paged Pool Area          | ページング可能なメモリ領域                                           |
| FFFFF90000000000       | FFFFF97FFFFFFFFF         | 512GB     | Session Space            |                                                        |
| FFFFF98000000000       | FFFFFa70FFFFFFFF         | 1TB       | Dynamic Kernel VA Space  | 動的メモリ領域                                           |
| FFFFFa8000000000       | *nt!MmNonPagedPoolStart-1 | 6TB Max   | PFN Database             | PFN 関連の情報を格納する                                      |
| *nt!MmNonPagedPoolStart | *nt!MmNonPagedPoolEnd     | 512GB Max | Non-Paged Pool           | ページングされないメモリ領域(ディスクにスワップアウトされない)                     |
| FFFFFFFFFFc00000       | FFFFFFFFFFFFFFFF         | 4MB       | HAL and Loader Mappings  | ハードウェア抽象化レイヤとローダが使う領域                             |

#### _MMPFN:物理ページフレーム

Linux kernel が `page` 構造体の配列で物理メモリを表すのと同様に、NT kernel では `_MMPFN` 構造体で**物理ページ 1 枚**を表し、**構造体の配列**で**すべての物理メモリページ**を管理します。配列の添字がそのまま物理ページの**ページフレーム番号**(Page Frame Number、PFN)で、この配列が `PFN Database` 領域です。グローバルなポインタ変数 `_MMPFN* MmPfnDatabase` に、この配列のアドレスが格納されています。

![](https://s2.loli.net/2025/02/01/DjXOsiKcuGe3F62.png)

Page の用途に応じて、active でないページに対応する `_MMPFN` は異なるリストに入れられ、リストの先頭は `_MMPFNLIST` 構造体です。

- `MmZeroedPageListHead`:ゼロクリア済みの空きページのリスト
- `MmFreePageListHead`:通常の空きページのリスト。システムがアイドルのときに、ここからページを取り出してゼロクリアし、`MmZeroedPageListHead` に置く
- `MmStandbyPageListHead`:プロセスがワーキングセット(working set、つまり**プロセスの仮想アドレス空間のうち物理メモリに常駐しているページの集合**)からページを破棄するとき、ページが変更されていなければこのリストに入れる。free リストと zeroed リストがどちらも空のとき、ここからページを確保する
- `MmModifiedPageListHead`:プロセスがワーキングセットからページを破棄するとき、ページが変更されていて、ディスクへの書き戻しが必要ならこのリストに入れる。modified page writer が処理を終えると、ページは standby リストに置かれる
- `MmModifiedNoWritePageListHead`:プロセスがワーキングセットからページを破棄するとき、ページが変更されていて、ディスクへの書き戻しが**不要**ならこのリストに入れる。modified page writer が処理を終えると、ページは standby リストに置かれる
- `MmBadPageListHead`:これらのページには何らかの障害がある可能性がある

> プロセスがワーキングセットからページを破棄する理由は 2 つあります。1 つは元のワーキングセットがいっぱいで新しいページを取り込む必要があるとき、もう 1 つはメモリマネージャがワーキングセットをトリミングしたとき(たとえばメモリが足りなくなったとき)です。
>
> プロセスの終了時には、すべてのページが freepagelist リストに入ります。

![](https://s2.loli.net/2025/02/01/F31JSlV7XCruWyT.png)

ページが異なるリスト間を循環する様子の全体図は次のとおりです。

![](https://s2.loli.net/2025/02/01/p2amPDjBd34IZYk.png)

`_MMPFN` 構造体も多くの union を使っており、ページが異なるリスト間を循環するとき、`_MMPFN` の異なるオフセットのフィールドは異なる意味を持ちます。

![image.png](https://s2.loli.net/2023/12/29/JqmC3DZRiVpMPbB.png)

#### ページビットマップ

> 執筆中。

### 二、Pool Memory(before 19H1)

Windows NT kernel は、ページを用途に応じて異なる「**プール**」(Pool)に分けて管理し、これらのページをより細かい粒度の小さなオブジェクトに分割してカーネルコンポーネントに使わせます。プールの種類は全部で 3 つあります。

- ノンページドプール(Non Paged Pool):このプールのページは物理メモリに常駐し、ディスクにスワップアウトされない
- ページドプール(Paged Pool):このプールのページは、メモリが逼迫するとディスクにスワップアウトされる可能性がある
- セッションページドプール(Session Paged Pool):このプールのページは、メモリが逼迫するとディスクにスワップアウトされる可能性があり、セッション間は隔離されている

#### 基本単位:プールブロック(Pool Block)

プールメモリで 1 回の確保ごとに得られるオブジェクトをプールブロック(Pool Block)と呼びます。ptmalloc2 の chunk に似ており、各プールブロックのデータの前部には、次のデータを格納する header があります。

- Previous Size:隣接する低アドレス側のプールブロックのサイズを**4 ビット右シフトした結果**
- Pool Index:プールブロックが属するプールディスクリプタグループのインデックス。複数のプールディスクリプタでプールディスクリプタ配列を構成する
- Block Size:プールブロックのサイズを**4 ビット右シフトした結果**
- Pool Type:プールブロックが属するプールの種類
- Pool Tag:デバッグ時に識別に使う文字
- (union が 1 つ):
    - Process Billed:このプールブロックを確保したプロセスのディスクリプタ `_EPROCESS` へのポインタ
    - (構造体が 1 つ)
        - Allocator Back Trace Index:
        - Pool Tag Hash:

また、Windows Server 2003 から、潜在的な chunk overflow を防ぐために、Pool Chunk の末尾に Canary フィールドが導入されました。この値は ( _これ以上の情報は見つからなかったが、プールブロックの確保と解放の際と推測される_ ) にチェックされます。

![](https://s2.loli.net/2025/02/01/abBQ3WwxVCvdPj8.png)

> Pool Chunk が使われるのは、要求されたメモリサイズが 4080 バイト以下の場合だけです(16 バイトの header を加えるとちょうどメモリページ 1 枚分)。

Pool Chunk の管理は ptmalloc2 の chunk と非常によく似ており、NT kernel では Freed Chunk の Data フィールドを再利用して、Free Chunk を単方向または双方向のリストとして構成します。

![](https://s2.loli.net/2025/02/03/MoOTksItJ6Wvdmr.png)

#### プールディスクリプタ:カーネル共有メモリプール

> この構造は Windows 10 の複数のバージョンの間でも、大小さまざまな変化を経ています。ただし重要な変化は 1809 から 1903(19H1)にかけてのもので、1903 から NT kernel はカーネルの動的メモリアロケータとして Segment Heap の仕組みを導入しました。そのためこの節では、主にプールメモリアロケータをまだ使っていた 1809 以前の 64 ビット版について説明します。

Linux kernel の `kmem_cache` に似て、Windows kernel では 1 つのメモリプールを `_POOL_DESCRIPTOR` 構造で表します。構造は下図のとおりです。

![](https://s2.loli.net/2025/02/05/lcemqOtFIfyMCVa.png)

プールディスクリプタに対応するメモリプールはカーネル全体で共有され、特に重要なリストは 2 つあります。

- ListHeads リスト配列:解放後の通常のプールブロックを格納し、双方向リストで接続されており、プールブロックのサイズに応じて異なるサブリストに入れられる
- PendingFrees リスト:メモリプールに `DELAY_FREE` フラグが設定されている場合、プールブロックは解放後にまずこの単方向リスト(サイズ無制限)につながれ、リストの深さが指定値を超えたときにまとめて回収される

初期状態のメモリプールディスクリプタは、すべて `nt!PoolVector` 配列に置かれています。

#### コア専用メモリプール:Lookaside Lists

プールディスクリプタに対応するメモリプールはすべてのコアで共有されるため、コア数が増えると効率が壊滅的になります。そこで、各コアには実際には専用のメモリプールもあり、カーネルモードの GS レジスタが指す `プロセッサ制御領域`(Process Control Region、`_KPCR` 構造体で、Linux の `.percpu` セクションに似ている)に格納されています。Lookaside Lists は現在のコアのプールメモリ要求を優先的に処理するもので、それで足りない場合にだけ共有メモリプールにメモリを要求します。

LookasideList の構造は下図のとおりで、サイズに応じて配列上の異なるリストに属し、各リストはさらに 2 つのサブリストに分かれます。単方向リスト(デフォルト、長さに上限あり、LIFO)と、双方向リスト(前者がいっぱいのときにここに置く)です。LookasideList の配列のメンバ数は少ないため、小さなメモリの確保にだけ使われます。

![](https://s2.loli.net/2025/02/05/VBuc9hZysC2fbr4.png)

LookasideList は全部で 4 種類あります(`PP == Per Processsor`)。

- PPLookasideList:頻繁に確保・解放されるオブジェクト用の LookasideList
- PPNxPagedLookasideList:ノンページドプールの non-eXecuted ページの LookasideList
- PPNPagedLookasideList:ノンページドプールの LookasideList
- PPPagedLookasideList:ページドプールの LookasideList

> PPLookasideList とほかの LookasideList は何が違うのか。筆者もわかりません ~~、Windows がオープンソースになる日を待ちましょう~~ ......

#### メモリ確保の基本アルゴリズム

##### 1. メモリ要求の順序

プールメモリの確保の中核となる関数は `ExAllocatePoolWithTag(POOL_TYPE PoolType,SIZE_T NumberOfBytes,ULONG Tag)` で、ユーザーは確保するプールの種類や必要なメモリサイズなどの情報を手動で指定する必要があります。カーネルコンポーネントやドライバは、通常この API か、より上位のラッパーを通じてカーネル内のメモリ確保要求を行います。

- 汎用のプールメモリ確保が使えるのは 4080 バイト未満のメモリ要求だけで、これより大きいメモリ要求は内部で `nt!ExpAllocateBigPool()` によって処理される
- まず、要求されたプールの種類に応じて、`_KPCR` の LookasideList 領域の各リストからメモリを確保しようとし、満たせればそのまま返す
- LookasideList で満たせない場合は、対応するプールをロックし、ListHeads リストから確保しようとする。確保したプールブロックが必要なサイズより大きければ 2 つに分割し、1 つをユーザーに返して、もう 1 つを ListHeads リストに戻す
- 利用可能なプールブロックがない場合は、`nt!MiAllocatePoolPages` を呼び出してメモリページを確保し、2 つに分割して、1 つをユーザーに返し、もう 1 つを ListHeads リストに戻す


##### 2. プールブロックの分割方法:ページ境界にアラインされていないブロックは末尾から分割する

プールブロックを分割するとき、カーネルはまずプールブロックのアドレスを確認します。メモリページサイズ(0x1000)にアラインされていれば、先頭からユーザーが必要とするプールブロックを分割し、そうでなければ末尾からユーザーが必要とするプールブロックを切り出します。

![](https://s2.loli.net/2025/02/05/tNK6CdgSholBeq4.png)

#### メモリ解放の基本アルゴリズム

プールメモリの解放の中核となる関数は `ExFreePoolWithTag( PVOID Entry, ULONG Tag)` で、カーネルコンポーネントやドライバは、通常この API か、より上位のラッパーを通じてカーネル内のメモリ解放要求を行います。

Chunk header には、その Chunk が属する Pool Type & Index が格納されているため、解放時に属する Pool と対応する List を直接判断できます。具体的な解放の流れは次のとおりです。

- まず、その Chunk がページの最初の Chunk(ページ境界にアライン)かを確認し、そうなら `nt!MiFreePoolPages()` による回収を試み、成功すればそのまま返す
- 次に、物理的に隣接する高アドレス側の Chunk の PrevSize が、この Chunk の header に記録された Size と等しいかを確認し、等しくなければエラーとする
- Size が特定の値より小さければ、対応する Lookaside List に戻すことを試みる
- 対応する Pool に `DELAY_FREE` フラグが設定されていれば、PendingFrees List に戻す(PendingFreeDepth が特定の値より大きい場合は、先に `nt!ExDeferredFreePool` 関数を呼び出して PendingFrees List を空にする)
- 隣接する低アドレス側と高アドレス側の Chunk の状態を確認し、空きブロックを統合する。ここでは_次のメモリページの先頭の Chunk とは統合されない_ ことに注意
- 最後に、その Chunk があるページが空きページかを確認し、そうなら `nt!MiFreePoolPages()` を呼び出して回収し、そうでなければ対応する ListHeads リストに戻す

### 三、Segment Heap in Kernel(from 19H1)

**NT kernel 19H1 から、ユーザーモードの Segment Heap の確保ロジックがカーネルに導入されました。**

> 執筆中。

## システムコール

### 一、システムコールの経路

Linux のシステムコールと同様に、Windows ではカーネルがユーザーモードプロセスに提供するサービスを**システムサービス**(system service)と呼び、システムサービスへのすべての呼び出しは、`ntdll.dll` を通じてカーネルに入ります。

![Notepad によるファイル作成を例にした Windows のシステムコールの経路](https://s2.loli.net/2025/02/01/cbfeQk6OagNXMZP.png)

> `ntdll.dll` 内の `Nt` で始まる関数と `Zw` で始まる関数はいずれもシステムコールで、本質的に違いはありません。

システムサービス `NtDeleteFile` を例にとると、syscall 命令がサポートされていれば `syscall` 命令でカーネルに入り、そうでなければ `int 0x2E` のソフトウェア割り込みで割り込みゲートを通ってカーネルに入ります。

![](https://s2.loli.net/2025/02/01/byVx3MwQfCKJavL.png)

> `0x7FFE0000` のこの領域は**カーネルとユーザープロセスが共有するメモリ**(書き込み権限はカーネルだけが持つ)で、`KUSER_SHARED_DATA` 構造体であり、カーネルがユーザーモードに情報を提供するために使います。
>
> オフセット `0x308` には、そのアーキテクチャが `syscall` 命令をサポートしているかを示すブール値が格納されています。

Windows のシステムコールのカーネル側のエントリは `KiSystemCall64()` 関数に設定されています。`syscall` 命令/`0x2E` ソフトウェア割り込みが行われると、CPU は ring0 に切り替わり、この関数を統一的なシステムコールのエントリポイントとして実行します。この関数は `ntoskrnl.exe` で定義されており、`rax` レジスタが指定するシステムコール番号に従って、SSDT 内の対応するカーネル関数を呼び出します。

![](https://s2.loli.net/2025/02/01/VLWQjOwufy8UnT4.png)

> 注:システムコールのエントリが `kiSystemCall64Shadow()` 関数になっていることもありますが、この関数も最終的には `kiSystemCall64()` 内の `KiSystemServiceUser` ラベルにジャンプします。

### 二、システムサービスディスクリプタテーブル

#### SSDT の基本構造

`ntoskrnl.exe` 内の `KiSystemCall64()` 関数をリバース解析すると、`KeServiceDescriptorTable` と `KeServiceDescriptorTable` の 2 つの変数を参照していることがわかります。これが**システムサービスディスクリプタテーブル**(System Service Descriptor Table、略して `SSDT`)で、**異なるシステムコール番号に対応するシステムコール関数**を格納します。

![](https://s2.loli.net/2025/02/01/AycmGR8wENvHjeg.png)

その本質は `tag_SERVICE_DESCRIPTOR_TABLE` 構造体で、4 つのサブテーブルからなる `SYSTEM_SERVICE_TABLE` **構造体の配列**です。

```c
typedef struct tag_SERVICE_DESCRIPTOR_TABLE {
    SYSTEM_SERVICE_TABLE nt;		// KeServiceDescriptorTable ではこのテーブルだけ
    SYSTEM_SERVICE_TABLE win32k;	// KeServiceDescriptorTableShadow ではこのテーブルが追加で使われる
    SYSTEM_SERVICE_TABLE sst3;
    SYSTEM_SERVICE_TABLE sst4;
} SERVICE_DESCRIPTOR_TABLE;
```

`SYSTEM_SERVICE_TABLE` 構造体の定義は次のとおりで、そのうち `ServiceTable` メンバが実質的なシステムコールテーブルです。

```c
typedef struct tag_SYSTEM_SERVICE_TABLE {
    PULONG      ServiceTable;	// 実際のシステムコールテーブル
    PULONG      CounterTable;	// 
    ULONG       ServiceLimit;	// システムコールの数
    PCHAR       ArgumentTable;	// 引数の数のテーブル
} SYSTEM_SERVICE_TABLE;
```

![](https://s2.loli.net/2025/02/01/vNFWB1j9YVIZEdH.png)

`ServiceTable` メンバは**実際には【対象関数のシステムコールテーブルからのオフセット】の配列へのポインタで、各項目は 4 バイト**です。ただし実際の計算では、_この値をまず 4 ビット右シフトしてから_ _システムコールテーブルの先頭アドレス_ に加算して、システムコールの実際のアドレスを得ます。つまり次のとおりです。
$$
Addr_{syscall} = Addr_{ServiceTable} + (ServiceTable[syscall\_nr] >> 4)
$$

これにより、SSDT の基本構造は次の図のようになります(`NtOpenFile()` システムコールを例とする)。

![](https://s2.loli.net/2025/02/01/J4bHB6uQV1nOFMA.png)

Windbg で確認します。

![](https://s2.loli.net/2025/02/01/IgC4Fm9ZYnhp7WQ.png)

ここで 4 ビットの左右シフトという不思議な操作をする理由は、次のとおりです。

- **セキュリティ上の理由**:SSDT 経由で呼び出されるシステムコールの範囲が、SSDT 付近の 4G のオフセット内に制限されます。ドライバのアドレス空間の間隔は少なくとも 4GB あり、SSDT のアドレスはコードにハードコードされているため、SSDT のハイジャックをうまく防げ、攻撃の難度が上がります。
- **スタック上の引数の数の格納**:NT kernel のシステムコールには引数が 6 個を大きく超えるものが多く、スタックで引数を渡す必要があります。この 4 ビットは、各システムコールが**スタックで渡す引数の数**を記録するために使われます。

#### _Shadow SSDT:GUI プログラム用の SSDT_

**シャドウシステムサービスディスクリプタテーブル**(Shadow System Service Descriptor Table、略して `Shadow SSDT`)は、**GUI プログラム専用の SSDT** です。SSDT と比べて、グラフィック関連のシステムコールを担当するサブテーブル `W32pServiceTable` が追加されており、これは `win32k.sys`、つまり**グラフィックサブシステム**にあります。

> SSDT と Shadow SSDT の最初のサブテーブルはどちらも `KiServiceTable` で、NT kernel の通常のシステムコールに対応します。

![ここで SystemServiceTable を指しているのはポインタではなく、展開された値であることに注意](https://s2.loli.net/2025/02/01/vBinIhjLrtHElw2.png)

アプリケーションが Windows でシステムコールを行うとき、どちらの大テーブルを呼び出すかは、スレッド制御ブロック(`KTHREAD`)の対応するフラグが決めます。`eax` レジスタの 13 ~ 12 ビットがどのサブテーブルを呼び出すかの指定に使われ、下位 12 ビットがテーブル内の具体的なシステムコールの指定に使われます。

![](https://s2.loli.net/2025/02/01/7EsiL5ednOkg1Y8.png)

> #### _補足:KeServiceDescriptorTableFilter_
>
> このテーブルは Windows 10 から導入されました。KTHREAD に `RestrictedGuiThread` フラグが設定されている場合は、Shadow SSDT の代わりにこのテーブルが使われますが、現時点でこのテーブルに関する資料はまだ少ないです(🕊)

## プロセス管理

### 一、NT kernel のプロセスとスレッド

Windows NT kernel では、プロセスを `_EPROCESS` 構造体で表します。Linux の `task_struct` に似ており、この構造体に Windows プロセスのすべての情報が格納されます。すべてのプロセスの `_EPROCESS` は双方向リストを構成します。

カーネルモードの GS レジスタは `プロセッサ制御領域`(Process Control Region)を指します。これは Linux の `.percpu` セクションに似ており、現在のスレッド制御ブロックへのポインタが格納されていて、その中にさらに現在のプロセス制御ブロックへのポインタが格納されています。

![](https://s2.loli.net/2025/02/01/a5lbF1fgDAUErcz.png)

### 二、Token:プロセスの権限クレデンシャル

Linux が `task_struct` の `cred` 構造体でプロセスの権限を表すのと同様に、NT kernel では `_Token` 構造体でプロセスの権限を表します。

> 執筆中。

## Reference

https://arttnba3.cn/

[Microsoft Learn. Spark possibility. ](https://learn.microsoft.com/en-us/)

『Windows カーネルの原理と実装』(原題:windows 内核原理与实现)——潘爱民 著

[CodeMachine - Windows Object Headers](https://codemachine.com/articles/object_headers.html)

[BlackHat USA 2021  - Windows Heap‐Backed Pool](https://i.blackhat.com/USA21/Wednesday-Handouts/us-21-Windows-Heap-Backed-Pool-The-Good-The-Bad-And-The-Encoded.pdf)

[CodeMachine - Kernel Virtual Address Layout](https://codemachine.com/articles/x64_kernel_virtual_address_space_layout.html)

[[原创]Windows内存篇Ⅱ x64内核内存布局的迁移演变 ](https://bbs.kanxue.com/thread-262931-1.htm)

[Page Frame Number Database](https://flylib.com/books/en/4.491.1.69/1/)

[Windows 系统调用分析与免杀实现](https://myzxcg.com/2022/01/Windows-%E7%B3%BB%E7%BB%9F%E8%B0%83%E7%94%A8%E5%88%86%E6%9E%90%E4%B8%8E%E5%85%8D%E6%9D%80%E5%AE%9E%E7%8E%B0/)

[A Syscall Journey in the Windows Kernel](https://alice.climent-pommeret.red/posts/a-syscall-journey-in-the-windows-kernel/)

[Windows Internals](https://github.com/Faran-17/Windows-Internals)

[探索Windows内核系列——句柄，利用句柄进行进程保护](https://tttang.com/archive/1682/)

[AngelBoy——Windows Kernel Heap: Segment heap in windows kernel Part 1](https://speakerdeck.com/scwuaptx/windows-kernel-heap-segment-heap-in-windows-kernel-part-1)

[Inside Windows Page Frame Number (PFN) - Part 1](https://rayanfam.com/topics/inside-windows-page-frame-number-part1/)

[OSR - Windows Pool Manager](https://www.osr.com/nt-insider/2014-issue1/windows-pool-manager/)

[Exploit Development: Swimming In The (Kernel) Pool - Leveraging Pool Vulnerabilities From Low-Integrity Exploits, Part 1](https://connormcgarr.github.io/swimming-in-the-kernel-pool-part-1/)

[Kernel Pool Exploitation on Windows 7 - Tarjei Mandt](https://media.blackhat.com/bh-dc-11/Mandt/BlackHat_DC_2011_Mandt_kernelpool-wp.pdf)

[BlackHat USA 2012 - Windows 8 Heap Internals](https://media.blackhat.com/bh-us-12/Briefings/Valasek/BH_US_12_Valasek_Windows_8_Heap_Internals_Slides.pdf)

[Vergilius Project | Kernels](https://www.vergiliusproject.com/kernels)