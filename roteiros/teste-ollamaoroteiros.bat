$versoes = @{
A = @"
You extract the main visual subject of a narration sentence, to search for a stock photo.
Rules:
- Answer in ENGLISH only.
- 2 to 4 words, a concrete noun phrase that can be photographed.
- No punctuation, no explanation.
Examples:
Text: Imagine chegar em casa e encontrar um companheiro de peito largo. -> English bulldog
Text: Os trilhos de código 83 são mais finos que os de código 100. -> HO scale model railway track
"@
B = @"
You extract the main visual subject of a narration sentence, to search for a stock photo.
Rules:
- Answer in ENGLISH only.
- 2 to 4 words, a concrete noun phrase that can be photographed.
- Keep the specific breed, object or material named in the text when there is one.
- No punctuation, no explanation.
Examples:
Text: Imagine chegar em casa e encontrar um companheiro de peito largo. -> English bulldog
Text: O focinho curto do bulldog dificulta a respiração. -> English bulldog face close up
Text: Dormentes de madeira sustentam os trilhos sobre o leito de cortiça. -> wooden railway ties on cork roadbed
"@
}

$casos = @(
  @{ t = "Imagine chegar em casa e encontrar um companheiro de peito largo, focinho enrugado e olhar expressivo."; ok = "bulldog" },
  @{ t = "Entretanto, a primeira surpresa aparece quando o calor aumenta. Seu focinho curto dificulta a respiração."; ok = "bulldog|nose|face|snout" },
  @{ t = "Dentro de casa, esse cão costuma apreciar a companhia humana, os momentos de descanso e passeios moderados."; ok = "bulldog|dog" },
  @{ t = "Os trilhos de código 83 são mais finos que os de código 100."; ok = "track|rail" },
  @{ t = "Dormentes de madeira sustentam os trilhos sobre o leito de cortiça."; ok = "tie|sleeper|cork|wood" }
)

foreach ($nome in $versoes.Keys | Sort-Object) {
  Write-Host "`n=== Versão $nome ===" -ForegroundColor Cyan
  $tempos = @()
  foreach ($c in $casos) {
    $body = @{
      model = "qwen2.5-coder:3b"; stream = $false; keep_alive = "30m"
      messages = @(@{ role = "system"; content = $versoes[$nome] }, @{ role = "user"; content = "Text: $($c.t)" })
      options = @{ temperature = 0; num_predict = 14 }
    } | ConvertTo-Json -Depth 6
    $t = Measure-Command { $r = Invoke-RestMethod -Uri http://localhost:11434/api/chat -Method Post -Body $body -ContentType "application/json" }
    $resp = $r.message.content.Trim()
    $palavras = ($resp -split '\s+' | Where-Object { $_ }).Count
    $ingles = $resp -notmatch '[áéíóúãõçâêôà]'
    $contem = $resp -match $c.ok
    $pontos = [int]($ingles) + [int]($palavras -ge 2 -and $palavras -le 4) + [int]($resp -notmatch '[.,:;!?"]') + [int]$contem
    $tempos += $t.TotalSeconds
    "{0,5:N2}s  pts={1}/4  ->  {2}" -f $t.TotalSeconds, $pontos, $resp
  }
  "Tempo médio: {0:N2}s" -f (($tempos | Measure-Object -Average).Average)
}




$versoes = @{
A = @"
You extract the main visual subject of a narration sentence, to search for a stock photo.
Rules:
- Answer in ENGLISH only. Never Portuguese words, even in the middle of the phrase.
- Exactly 2 to 4 words, a concrete noun phrase that can be photographed.
- Keep the exact breed or object named in the text. Never replace a breed with another one.
- No punctuation, no explanation.
Examples:
Text: Imagine chegar em casa e encontrar um companheiro de peito largo. -> English bulldog
Text: O focinho curto do bulldog dificulta a respiração. -> bulldog face close up
Text: Dormentes de madeira sustentam os trilhos sobre o leito de cortiça. -> wooden railway ties
"@
}

$casos = @(
  @{ t = "Imagine chegar em casa e encontrar um companheiro de peito largo, focinho enrugado e olhar expressivo."; ok = "bulldog" },
  @{ t = "Entretanto, a primeira surpresa aparece quando o calor aumenta. Seu focinho curto dificulta a respiração."; ok = "bulldog|nose|face|snout" },
  @{ t = "Dentro de casa, esse cão costuma apreciar a companhia humana, os momentos de descanso e passeios moderados."; ok = "bulldog|dog" },
  @{ t = "Os trilhos de código 83 são mais finos que os de código 100."; ok = "track|rail" },
  @{ t = "Dormentes de madeira sustentam os trilhos sobre o leito de cortiça."; ok = "tie|sleeper|cork|wood" }
)

foreach ($nome in $versoes.Keys | Sort-Object) {
  Write-Host "`n=== Versão $nome ===" -ForegroundColor Cyan
  $tempos = @()
  foreach ($c in $casos) {
    $body = @{
      model = "qwen2.5-coder:3b"; stream = $false; keep_alive = "30m"
      messages = @(@{ role = "system"; content = $versoes[$nome] }, @{ role = "user"; content = "Text: $($c.t)" })
      options = @{ temperature = 0; num_predict = 14 }
    } | ConvertTo-Json -Depth 6
    $t = Measure-Command { $r = Invoke-RestMethod -Uri http://localhost:11434/api/chat -Method Post -Body $body -ContentType "application/json" }
    $resp = $r.message.content.Trim()
    $palavras = ($resp -split '\s+' | Where-Object { $_ }).Count
    $ingles = $resp -notmatch '[áéíóúãõçâêôà]'
    $contem = $resp -match $c.ok
    $pontos = [int]($ingles) + [int]($palavras -ge 2 -and $palavras -le 4) + [int]($resp -notmatch '[.,:;!?"]') + [int]$contem
    $tempos += $t.TotalSeconds
    "{0,5:N2}s  pts={1}/4  ->  {2}" -f $t.TotalSeconds, $pontos, $resp
  }
  "Tempo médio: {0:N2}s" -f (($tempos | Measure-Object -Average).Average)
}


$versoes = [ordered]@{
A = @"
You extract the main visual subject of a narration sentence, to search for a stock photo.
Rules:
- Answer in ENGLISH only.
- 2 to 4 words, a concrete noun phrase that can be photographed.
- No punctuation, no explanation.
Examples:
Text: Imagine chegar em casa e encontrar um companheiro de peito largo. -> English bulldog
Text: Os trilhos de código 83 são mais finos que os de código 100. -> HO scale model railway track
"@
B2 = @"
You extract the main visual subject of a narration sentence, to search for a stock photo.
Rules:
- Answer in ENGLISH only. Never Portuguese words, even in the middle of the phrase.
- Exactly 2 to 4 words, a concrete noun phrase that can be photographed.
- Keep the exact breed or object named in the text. Never replace a breed with another one.
- No punctuation, no explanation.
Examples:
Text: Imagine chegar em casa e encontrar um companheiro de peito largo. -> English bulldog
Text: O focinho curto do bulldog dificulta a respiração. -> bulldog face close up
Text: Dormentes de madeira sustentam os trilhos sobre o leito de cortiça. -> wooden railway ties
"@
}

# Critério esperado: termo que tem que aparecer. "ok" é obrigatório quando o texto cita o item.
$casos = @(
  @{ t = "Imagine chegar em casa e encontrar um companheiro de peito largo, focinho enrugado e olhar expressivo."; ok = "bulldog" },
  @{ t = "Entretanto, a primeira surpresa aparece quando o calor aumenta. Seu focinho curto dificulta a respiração."; ok = "bulldog|nose|face|snout" },
  @{ t = "Dentro de casa, esse cão costuma apreciar a companhia humana, os momentos de descanso e passeios moderados."; ok = "dog" },
  @{ t = "Os trilhos de código 83 são mais finos que os de código 100."; ok = "track|rail" },
  @{ t = "Dormentes de madeira sustentam os trilhos sobre o leito de cortiça."; ok = "tie|sleeper|cork|wood" }
)

# Palavras de português que nunca deveriam aparecer na resposta em inglês.
$ptPalavras = '\b(de|do|da|dos|das|com|para|uma|um|os|as|sobre|trilhos|trilho|código|casa|cão|focinho|curto|leito|madeira|em|e|o|a)\b'

foreach ($nome in $versoes.Keys) {
  Write-Host "`n=== Versão $nome ===" -ForegroundColor Cyan
  $tempos = @(); $total = 0
  foreach ($c in $casos) {
    $body = @{
      model = "qwen2.5-coder:3b"; stream = $false; keep_alive = "30m"
      messages = @(@{ role = "system"; content = $versoes[$nome] }, @{ role = "user"; content = "Text: $($c.t)" })
      options = @{ temperature = 0; num_predict = 14 }
    } | ConvertTo-Json -Depth 6
    $t = Measure-Command { $r = Invoke-RestMethod -Uri http://localhost:11434/api/chat -Method Post -Body $body -ContentType "application/json" }
    $resp = $r.message.content.Trim()
    $palavras = ($resp -split '\s+' | Where-Object { $_ }).Count
    $pontos = [int]($resp -notmatch $ptPalavras) + [int]($palavras -ge 2 -and $palavras -le 4) + [int]($resp -notmatch '[.,:;!?"]') + [int]($resp -match $c.ok)
    $tempos += $t.TotalSeconds; $total += $pontos
    "{0,5:N2}s  pts={1}/4  ->  {2}" -f $t.TotalSeconds, $pontos, $resp
  }
  "Média de pontos: {0:N2}/4   |   tempo médio: {1:N2}s" -f ($total / $casos.Count), (($tempos | Measure-Object -Average).Average)
}