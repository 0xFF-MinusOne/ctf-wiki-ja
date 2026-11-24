# Introduction

カーネルの権限昇格(privilege escalation)とは、一般ユーザーが root ユーザーの権限を取得し、本来は制限されていたリソースにアクセスできるようになることです。ここでは、権限昇格の方法を 2 つの観点から考えます。

- 自分自身を変える:自プロセスの権限を変更して、root 権限を持たせる。
- 他者を変える:高い権限を持つプロセスの実行に干渉して、こちらの望む処理を行わせる。

## 参考文献

- https://en.wikipedia.org/wiki/Privilege_escalation
