# F003 — Importação de Vinhos via Planilha

> Status: ready | Versão: 1.0 | Sprint: 2

## Objetivo

Permitir que o restaurante importe múltiplos rótulos de uma vez via arquivo .xlsx ou .csv, acelerando o onboarding inicial.

## Atores

- **Gerente**: faz upload da planilha
- **Sistema**: valida, processa e reporta erros por linha

## Pré-condições

- Restaurante ativo com gerente autenticado
- Planilha no formato do template disponibilizado pela Vinia

---

## Regras de Negócio

- RN01: Arquivo aceito: `.xlsx` ou `.csv` (UTF-8)
- RN02: Tamanho máximo do arquivo: 10MB
- RN03: Limite de linhas por importação: 500 rótulos
- RN04: A primeira linha do arquivo deve ser o cabeçalho (ignorado no processamento)
- RN05: Campos obrigatórios por linha: `name`, `producer`, `country`, `type`, `price`
- RN06: Linhas com erro são ignoradas e reportadas — linhas válidas são importadas normalmente
- RN07: Uvas na coluna `grapes` são separadas por vírgula: `"Cabernet Sauvignon, Merlot"`
- RN08: Importação é idempotente por nome+produtor+safra: se já existe, atualiza em vez de duplicar
- RN09: O processamento ocorre de forma assíncrona via Job para não travar a requisição
- RN10: Ao concluir, o gerente recebe notificação na interface com o resultado

## Template da Planilha

| Coluna | Header | Obrigatório | Exemplo |
|---|---|---|---|
| A | name | sim | Château Margaux |
| B | producer | sim | Château Margaux |
| C | vintage | não | 2018 |
| D | country | sim | França |
| E | region | não | Bordeaux |
| F | type | sim | tinto |
| G | grapes | não | Cabernet Sauvignon, Merlot |
| H | alcohol | não | 13.5 |
| I | price | sim | 850.00 |
| J | description | não | Vinho icônico de... |
| K | tasting_notes | não | Notas de cassis... |
| L | pairings | não | Carnes vermelhas, caça |
| M | available | não | true |

---

## Critérios de Aceite

### CA01 — Importação bem-sucedida
```
Dado que faço upload de planilha com 10 linhas válidas
Então um Job é disparado em background
E após conclusão vejo notificação: "10 rótulos importados com sucesso"
E os 10 rótulos aparecem na listagem do backoffice
```

### CA02 — Importação parcial com erros
```
Dado que a planilha tem 10 linhas, sendo 2 com price ausente
Então 8 rótulos são importados
E recebo relatório: "8 importados, 2 com erro"
E o relatório detalha: "Linha 5: preço obrigatório | Linha 9: preço obrigatório"
```

### CA03 — Idempotência
```
Dado que o rótulo "Château Margaux 2018" já existe
Quando importo planilha com essa mesma linha com preço atualizado
Então o rótulo existente é atualizado (não duplicado)
E o total de rótulos não aumenta
```

### CA04 — Arquivo inválido
```
Dado que faço upload de arquivo .pdf
Então recebo erro imediato: "Formato inválido. Envie .xlsx ou .csv"
E nenhum Job é disparado
```

### CA05 — Download do template
```
Dado que acesso a tela de importação
Quando clico em "Baixar template"
Então faço download de arquivo .xlsx com cabeçalho correto e 2 linhas de exemplo
```

---

## Componentes Laravel

### Job: `ImportWinesJob`
```php
// app/Jobs/ImportWinesJob.php
public function __construct(
    private Restaurant $restaurant,
    private string $filePath,   // path temporário no storage
    private int $userId         // para notificação ao concluir
)

public function handle(WineImportService $service): void
```

### Service: `WineImportService`
```php
// app/Services/WineImportService.php
public function import(Restaurant $restaurant, string $filePath): ImportResult
public function validate(array $row, int $lineNumber): array  // retorna erros ou []
public function downloadTemplate(): StreamedResponse
```

### DTO: `ImportResult`
```php
// app/DTOs/ImportResult.php
public int $imported;
public int $updated;
public int $failed;
public array $errors;  // [['line' => 5, 'message' => 'preço obrigatório']]
```

### Livewire: `WineImport`
```
- Upload de arquivo com validação de extensão/tamanho no frontend
- Botão de download do template
- Exibição de progresso durante processamento
- Exibição do resultado (ImportResult) ao concluir
```

---

## Testes

| ID | Tipo | Descrição |
|---|---|---|
| T003-01 | Feature | Importar xlsx com 5 linhas válidas — 5 rótulos criados |
| T003-02 | Feature | Linhas com erro são ignoradas, válidas importadas |
| T003-03 | Unit | Linha sem `name` retorna erro de validação |
| T003-04 | Unit | Linha com `type` inválido retorna erro de validação |
| T003-05 | Feature | Rótulo duplicado é atualizado, não duplicado |
| T003-06 | Feature | Upload de PDF retorna erro imediato |
| T003-07 | Feature | Arquivo acima de 10MB retorna erro |
| T003-08 | Feature | Download do template retorna xlsx com cabeçalho correto |
| T003-09 | Job | Job processa corretamente e armazena ImportResult |
