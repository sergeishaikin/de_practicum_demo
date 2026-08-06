$DetailQuestionName = "Orders for Selected Country"

$ExistingDetailCard = $ExistingCards |
    Where-Object { $_.name -eq $DetailQuestionName } |
    Select-Object -First 1

if (-not $ExistingDetailCard) {
    $DetailPayload = @{
        name        = $DetailQuestionName
        description = "Original streaming order records filtered by country."
        display     = "table"

        dataset_query = @{
            type     = "native"
            database = [int]$Database.id

            native = @{
                query = @"
SELECT
    order_id,
    customer,
    amount,
    country,
    status,
    event_time,
    kafka_partition,
    kafka_offset
FROM marts.streaming_orders
WHERE country = {{country}}
ORDER BY event_time DESC
"@

                "template-tags" = @{
                    country = @{
                        id           = "country"
                        name         = "country"
                        "display-name" = "Country"
                        type         = "text"
                        required     = $true
                    }
                }
            }
        }

        visualization_settings = @{
            "table.pivot" = $false
        }

        collection_id = $null
    }

    $DetailCard = Invoke-RestMethod `
        -Method Post `
        -Uri "$MetabaseUrl/api/card" `
        -Headers $Headers `
        -ContentType "application/json" `
        -Body ($DetailPayload | ConvertTo-Json -Depth 20)

    Write-Host "Detail question created:" -ForegroundColor Green
    Write-Host "$MetabaseUrl/question/$($DetailCard.id)"
}
else {
    $DetailCard = $ExistingDetailCard
    Write-Host "Detail question already exists: $($DetailCard.id)"
}