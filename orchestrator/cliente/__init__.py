"""Cliente do RoqueShield: a CLI `roqueshield` e o servidor MCP por stdio.

Fala com um shield que já está rodando, pela API REST. Só usa httpx, typer e rich:
não importa o motor (`orchestrator.config`, banco, scanners), então dá para empacotar
sozinho depois.
"""
