param(
    [string]$MetabaseUrl = "http://localhost:13000",
    [string]$DatabaseName = "de-demo-postgres",
    [string]$ChartName = "Streaming Revenue by Country",
    [string]$DetailQuestionName = "Orders for Selected Country",

    [Parameter(Mandatory = $true)]
    [string]$Email,

    [Parameter(Mandatory = $true)]
    [SecureString]$Password
)

$ErrorActionPreference = "Stop"


function ConvertTo-PlainText {
    param(
        [Parameter(Mandatory = $true)]
        [SecureString]$SecureValue
    )

    $Pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR(
        $SecureValue
    )

    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR(
            $Pointer
        )
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($Pointer)
    }
}




function Find-CardByName {
    param(
        [AllowNull()]
        [AllowEmptyCollection()]
        [object[]]$Cards,

        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    if (-not $Cards -or $Cards.Count -eq 0) {
        return $null
    }

    return $Cards |
        Where-Object {
            $_ -and
            $_.name -eq $Name -and
            $null -ne $_.id
        } |
        Select-Object -First 1
}


function Save-MetabaseCard {
    param(
        [Parameter(Mandatory = $true)]
        [string]$BaseUrl,

        [Parameter(Mandatory = $true)]
        [hashtable]$RequestHeaders,

        [Parameter(Mandatory = $true)]
        [hashtable]$Payload,

        [Parameter(Mandatory = $true)]
        [string]$CardName,

        [object]$ExistingCard
    )

    $JsonBody = $Payload | ConvertTo-Json -Depth 40

    if ($ExistingCard -and $ExistingCard.id) {
        $CardId = [int]$ExistingCard.id
        $UpdateUrl = "$BaseUrl/api/card/$CardId"

        Write-Host (
            "Updating '{0}', card ID {1}..." -f
            $CardName,
            $CardId
        ) -ForegroundColor Cyan

        return Invoke-RestMethod `
            -Method Put `
            -Uri $UpdateUrl `
            -Headers $RequestHeaders `
            -ContentType "application/json" `
            -Body $JsonBody `
            -ErrorAction Stop
    }

    Write-Host "Creating '$CardName'..." -ForegroundColor Cyan

    return Invoke-RestMethod `
        -Method Post `
        -Uri "$BaseUrl/api/card" `
        -Headers $RequestHeaders `
        -ContentType "application/json" `
        -Body $JsonBody `
        -ErrorAction Stop
}


if ([string]::IsNullOrWhiteSpace($MetabaseUrl)) {
    throw "MetabaseUrl cannot be empty."
}

if ([string]::IsNullOrWhiteSpace($Email)) {
    throw "Email cannot be empty."
}

$MetabaseUrl = $MetabaseUrl.TrimEnd("/")
$PlainPassword = ConvertTo-PlainText -SecureValue $Password


try {
    #
    # 1. Authenticate
    #
    $SessionPayload = @{
        username = $Email
        password = $PlainPassword
    }

    $Session = Invoke-RestMethod `
        -Method Post `
        -Uri "$MetabaseUrl/api/session" `
        -ContentType "application/json" `
        -Body ($SessionPayload | ConvertTo-Json) `
        -ErrorAction Stop

    if (-not $Session.id) {
        throw "Metabase did not return a session ID."
    }

    $Headers = @{
        "X-Metabase-Session" = $Session.id
    }

    Write-Host "Authenticated with Metabase." -ForegroundColor Green


    #
    # 2. Find the PostgreSQL database
    #
    $DatabasesResponse = Invoke-RestMethod `
        -Method Get `
        -Uri "$MetabaseUrl/api/database" `
        -Headers $Headers `
        -ErrorAction Stop

    $Databases = @($DatabasesResponse.data)

    $Database = $Databases |
        Where-Object {
            $_.name -eq $DatabaseName -or
            (
                $_.engine -eq "postgres" -and
                $_.details.host -eq "de-demo-postgres" -and
                $_.details.dbname -eq "dwh"
            )
        } |
        Select-Object -First 1

    if (-not $Database) {
        $AvailableNames = (
            $Databases |
            ForEach-Object { $_.name }
        ) -join ", "

        throw (
            "Database '$DatabaseName' was not found. " +
            "Available databases: $AvailableNames"
        )
    }

    $DatabaseId = [int]$Database.id

    Write-Host (
        "Using database '{0}', ID {1}." -f
        $Database.name,
        $DatabaseId
    ) -ForegroundColor Green


    #
    # 3. Load existing questions
    #
    $CardsResponse = Invoke-RestMethod `
        -Method Get `
        -Uri "$MetabaseUrl/api/card" `
        -Headers $Headers `
        -ErrorAction Stop

    $ExistingCards = @()

    if ($null -ne $CardsResponse) {
        $HasDataProperty = (
            $CardsResponse.PSObject.Properties.Name -contains "data"
        )

        if ($HasDataProperty) {
            if ($null -ne $CardsResponse.data) {
                $ExistingCards = @($CardsResponse.data)
            }
        }
        else {
            $ExistingCards = @($CardsResponse)
        }
    }

    Write-Host (
        "Found {0} existing saved questions." -f
        $ExistingCards.Count
    )


    #
    # 4. Aggregate bar chart
    #
    $ChartPayload = @{
        name        = $ChartName
        description = "Live streaming revenue aggregated by country."
        display     = "bar"

        dataset_query = @{
            type     = "native"
            database = $DatabaseId

            native = @{
                query = @"
SELECT
    country,
    total_amount
FROM marts.streaming_country_totals
ORDER BY total_amount DESC
"@
                "template-tags" = @{}
            }
        }

        visualization_settings = @{
            "graph.dimensions"         = @("country")
            "graph.metrics"            = @("total_amount")
            "graph.x_axis.title_text"  = "Country"
            "graph.y_axis.title_text"  = "Total amount"
            "graph.show_values"        = $true
            "graph.show_goal"          = $false
            "graph.show_trendline"     = $false
        }

        collection_id = $null
    }

    $ExistingChart = Find-CardByName `
        -Cards $ExistingCards `
        -Name $ChartName

    $ChartCard = Save-MetabaseCard `
        -BaseUrl $MetabaseUrl `
        -RequestHeaders $Headers `
        -Payload $ChartPayload `
        -CardName $ChartName `
        -ExistingCard $ExistingChart

    if (-not $ChartCard.id) {
        throw "The aggregate chart was saved, but no card ID was returned."
    }

    Write-Host "Aggregate chart saved." -ForegroundColor Green
    Write-Host "$MetabaseUrl/question/$($ChartCard.id)"


    #
    # 5. Drill-down detail table
    #
    $DetailPayload = @{
        name        = $DetailQuestionName
        description = (
            "Original streaming orders. " +
            "The optional country parameter supports dashboard drill-down."
        )
        display = "table"

        dataset_query = @{
            type     = "native"
            database = $DatabaseId

            native = @{
                query = @'
SELECT
    order_id,
    customer,
    amount,
    country,
    status,
    event_time,
    kafka_timestamp,
    kafka_partition,
    kafka_offset,
    batch_id,
    updated_at
FROM marts.streaming_orders
WHERE 1 = 1
[[AND country = {{country}}]]
ORDER BY event_time DESC
'@

                "template-tags" = @{
                    country = @{
                        id             = "country"
                        name           = "country"
                        "display-name" = "Country"
                        type           = "text"
                        required       = $false
                    }
                }
            }
        }

        visualization_settings = @{}
        collection_id          = $null
    }

    $ExistingDetail = Find-CardByName `
        -Cards $ExistingCards `
        -Name $DetailQuestionName

    $DetailCard = Save-MetabaseCard `
        -BaseUrl $MetabaseUrl `
        -RequestHeaders $Headers `
        -Payload $DetailPayload `
        -CardName $DetailQuestionName `
        -ExistingCard $ExistingDetail

    if (-not $DetailCard.id) {
        throw "The detail question was saved, but no card ID was returned."
    }

    Write-Host "Detail question saved." -ForegroundColor Green
    Write-Host "$MetabaseUrl/question/$($DetailCard.id)"


    #
    # 6. Summary
    #
    Write-Host ""
    Write-Host "Metabase questions are ready." -ForegroundColor Green

    Write-Host ""
    Write-Host "Aggregate chart:"
    Write-Host "  Name: $ChartName"
    Write-Host "  URL:  $MetabaseUrl/question/$($ChartCard.id)"

    Write-Host ""
    Write-Host "Detail table:"
    Write-Host "  Name: $DetailQuestionName"
    Write-Host "  URL:  $MetabaseUrl/question/$($DetailCard.id)"

    Write-Host ""
    Write-Host "The detail table now supports:" -ForegroundColor Cyan
    Write-Host "  - no country parameter: show all orders"
    Write-Host "  - country=UK: show only UK orders"
    Write-Host "  - country=ES: show only Spanish orders"

    Write-Host ""
    Write-Host "Dashboard drill-down setup:" -ForegroundColor Cyan
    Write-Host "1. Create or open a Metabase dashboard."
    Write-Host "2. Add both saved questions."
    Write-Host "3. Add a dashboard filter named Country."
    Write-Host "4. Connect it to the detail question's country parameter."
    Write-Host "5. Edit the revenue chart card."
    Write-Host "6. Select Click behavior."
    Write-Host "7. Choose Update a dashboard filter."
    Write-Host "8. Map the clicked country value to the Country filter."
}
catch {
    Write-Host ""
    Write-Host "Metabase automation failed." -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red

    if (
        $_.ErrorDetails -and
        $_.ErrorDetails.Message
    ) {
        Write-Host $_.ErrorDetails.Message -ForegroundColor Red
    }

    throw
}
finally {
    $PlainPassword = $null
}