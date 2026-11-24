import base64
import json
import time

# Variável GLOBAL: fica fora do handler, então é criada uma única vez, na fase
# Init, quando o ambiente de execução (container) sobe. Se o mesmo ambiente for
# reaproveitado (warm start), o valor continua na memória entre as invocações.
contador = 0


def lambda_handler(event, context):
    """Gera uma guia de transporte de bolsas de sangue a partir de uma requisição."""
    global contador          # avisa ao Python que vamos alterar a variável global
    contador += 1            # conta quantas vezes ESTE ambiente já foi invocado

    # O API Gateway entrega o corpo HTTP como TEXTO em event["body"] (ou None).
    # "or '{}'" evita erro quando não vem body.
    corpo_texto = event.get("body") or "{}"
    # Às vezes o corpo chega codificado em base64 (o API Gateway sinaliza com
    # isBase64Encoded=true; o "sam local generate-event" 1.174.0 gera assim).
    if event.get("isBase64Encoded"):
        corpo_texto = base64.b64decode(corpo_texto).decode("utf-8")
    corpo = json.loads(corpo_texto)   # texto JSON -> dict do Python

    requisicao_id = corpo.get("requisicaoId")
    if not requisicao_id:
        return resposta(400, {"erro": "requisicaoId obrigatório"})

    # Simula um processamento lento para testar o Timeout configurado no template.
    if corpo.get("demorar") is True:
        time.sleep(5)

    return resposta(201, {
        "guia": "G-" + requisicao_id,
        "hospital": corpo.get("hospital"),
        "bolsas": corpo.get("bolsas"),
        "invocacaoNesteAmbiente": contador,
    })


def resposta(status, dados):
    """Monta a resposta no formato que o API Gateway (proxy) espera."""
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json; charset=utf-8"},
        "body": json.dumps(dados, ensure_ascii=False),
    }
