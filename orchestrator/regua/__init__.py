"""Régua de efetividade: quanto a ferramenta acerta, medido contra um gabarito.

Os testes provam que cada conserto funciona; a régua mede o resultado. Um gabarito
lista defeitos plantados (que TÊM de ser achados, e pelo motivo certo) e controles
limpos (código seguro em que um alarme é falso positivo). O placar dá, por camada,
o recall, os falsos positivos e o que ficou sem medir.
"""
