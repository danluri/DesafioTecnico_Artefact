# Grava as conversas de exemplo enviando mensagens ao console local do agente.
# Pré-requisito: console rodando com EMPORIO_LLM_PROVIDER=local-llama (ver README, seção "Como rodar").
# Uso (na raiz do repositório): powershell -ExecutionPolicy Bypass -File scripts/gravar-exemplos.ps1 -Saida exemplos-bruto.md
param(
    [string]$BaseUrl = "http://127.0.0.1:8080",
    [string]$Saida = "exemplos-bruto.md"
)
$ErrorActionPreference = "Stop"

# Cada conversa é uma lista de mensagens enviadas na mesma sessão.
$conversas = [ordered]@{
    "1. Catálogo com filtro de preço e acompanhamento" = @(
        "Oi! Quais opções de violões disponíveis custando até R`$1000?",
        "Gostei do mais barato. Quanto fica no PIX e em quantas vezes posso parcelar?"
    )
    "2. Informações gerais da loja" = @(
        "Qual o endereço da loja?",
        "E vocês abrem no sábado? Até que horas?"
    )
    "3. Preço, promoção vencida e produto sem estoque" = @(
        "Quanto custa o Takamine GD20?",
        "Ele ainda está naquela Oferta Especial com desconto?",
        "E o Giannini GF-3D, tem em estoque?"
    )
    "4. Aplicação da política de devolução" = @(
        "Me arrependi da minha compra, posso devolver meu pedido?",
        "Comprei pelo site e recebi há 4 dias, ainda tá na caixa. Quem paga o frete?"
    )
    "5. Fora do escopo" = @(
        "Vocês vendem palhetas e cordas para guitarra?",
        "E você sabe me dizer qual a capital da França?"
    )
}

$linhas = New-Object System.Collections.Generic.List[string]
$linhas.Add("# Transcrição bruta — gerada em $(Get-Date -Format 'yyyy-MM-dd HH:mm')")
$contador = 0
foreach ($titulo in $conversas.Keys) {
    $linhas.Add(""); $linhas.Add("## $titulo"); $linhas.Add("")
    $sessao = $null
    foreach ($texto in $conversas[$titulo]) {
        $contador++
        $corpo = @{ text = $texto; message_id = "exemplo-$contador-$([guid]::NewGuid().ToString('N').Substring(0,8))" }
        if ($sessao) { $corpo.session_id = $sessao }
        $json = $corpo | ConvertTo-Json -Compress
        $inicio = Get-Date
        $r = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/messages" -TimeoutSec 400 `
            -ContentType "application/json; charset=utf-8" -Body ([Text.Encoding]::UTF8.GetBytes($json))
        $segundos = [math]::Round(((Get-Date) - $inicio).TotalSeconds, 1)
        $sessao = $r.session_id
        $linhas.Add("**Cliente:** $texto"); $linhas.Add("")
        $linhas.Add("**Agente:** $($r.response)"); $linhas.Add("")
        $linhas.Add("<sub>modelo=$($r.model) · outcome=$($r.outcome) · tool_calls=$($r.tool_calls) · policy_grounded=$($r.policy_grounded) · tempo=${segundos}s · trace_id=$($r.trace_id)</sub>")
        $linhas.Add("")
        Write-Host "[$titulo] $segundos s — $($r.outcome)"
    }
}
[IO.File]::WriteAllLines((Join-Path (Get-Location) $Saida), $linhas, (New-Object Text.UTF8Encoding($false)))
Write-Host "Transcrição salva em $Saida"
