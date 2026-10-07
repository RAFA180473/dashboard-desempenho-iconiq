# ICONIQ | Automatização do painel de desempenho

## Onde está
- Dashboard: https://claude.ai/artifact/LJ5pdWNvD92zUT7nKaH8G9 (privado; partilhar pelo menu Partilhar)
- Repositório: SharePoint › OPERAÇÕES › Dashboard Desempenho ICONIQ (01 Documentação, 02 Scripts de recolha, 03 Dados e backups)
- Cópia de trabalho: projeto Claude "Desempenho equipas ICONIQ 2026", pasta automatizacao

## Estado (07/10/2026)
- Dados WheelSys recolhidos de jan/2025 a 30/09/2026; meses até setembro fechados.
- Customer Verdict carregado de jan/2025 a 06/10/2026.
- Excel atualizado: Painel_ICONIQ_backup_ate_30set2026.xlsx (Base_Rentals + 4 406 contratos de ago–set, coluna P = Via Verde; Incremental Sales por chave em Vendas_Colaborador!Y:Z com fórmula em Q).
- Frota e ocupação: Fleet Utilization Report do WheelSys (frota média = dias disponíveis ÷ dias do mês; ocupação = dias em aluguer ÷ dias disponíveis), carregadas para jan/2025–set/2026 e no separador Fleet do Excel para ago–set/2026.

## Peças
- **Dashboard**: artifact "Desempenho ICONIQ" (https://claude.ai/artifact/LJ5pdWNvD92zUT7nKaH8G9). Lê os dados da base `meses/AAAA-MM` do próprio artifact.
- **Coletor WheelSys** (`coletor_wheelsys.js`): corre num separador do WheelSys (https://iconiqfleet.wheelsys.io/ui/) com sessão iniciada. Chama os mesmos pedidos dos relatórios (`/ui/reports/exreportpreview.aspx/GenerateReportData`), só leitura, e agrega por mês × estação × colaborador, sem dados pessoais de clientes.
- **Pipeline Python** (`atualizar_painel.py`): reconstrói os indicadores a partir do Painel_ICONIQ_backup.xlsx (validação e histórico).

## Relatórios WheelSys usados
| Relatório | browser | Filtros-chave | Uso |
|---|---|---|---|
| Detailed Rentals Report | detailedrentalreport | Date selection Check-ins (2), Closed contracts (1) | Turnover (chargenet), Net Rental (chargesubdisc), Rental Days (duration), fechados, danos (chargedamage), Diretos |
| Detailed Rentals Report | detailedrentalreport | Date selection Check-outs (1), All contracts (3) | Contratos abertos e dias dos contratos abertos |
| Extra Sales Report | extrasalesrpt | List type Check-outs (1), Sales User "Sold by" (1) | Vendas de extras ao balcão, por produto |
| Incremental Sales Report | incrementalsalesrpt | Date | Incremental Sales (campo total) por estação e colaborador |
| Fleet Utilization Report | fleetutilizationreport | Date basis (mês), Utilization per day | Frota média (avdays ÷ dias do mês), dias em aluguer (rentdays) e ocupação, por estação (campo station) |

Mapeamento confirmado com o Base_Rentals: Check-out Date=datefrom, Check-in Date=dateto, Days=duration, Net Rental=chargesubdisc, Damages=chargedamage, Net=chargenet, Check-out User=user_from_name, Check-in User=user_to_name, Booking User=user_res_name, Corporate=corporate_name, Rate code=ratecode, Agr. No=radocno.

## Regras (decididas com o Nuno, 07/10/2026)
- Receita, Net Rental e Rental Days: mês da Check-in Date, Check-out station, Check-out User.
- Abertos: Check-out Date (todos os contratos, incluindo os ainda ativos). Fechados e danos: Check-in Date e Check-in station.
- Diretos: Net Rental, Rate code DIRETOS, Corporate vazio, Booking User.
- Incremental Sales: usar o Incremental Sales Report do WheelSys tal como sai (substitui o input manual do Excel).
- Extras: venda = valor líquido > 0 por contrato e produto, vendido por colaborador (não "Account System"). Estornos abatem. Fora: VV (obrigatório), TOLLS e TOLL6 (portagens). FCI conta como pacote.
- Penetração = contratos com venda ÷ contratos abertos. Extras €/dia = receita de extras ÷ dias dos contratos abertos.
- Google Score substituído pelo Customer Verdict: NPS (promotores 9–10 menos detratores 0–6) e Experiência (média das 5 notas ×10), por mês do inquérito e estação de check-out; por colaborador via RA Number → Check-out User.
- Via Verde analisada à parte: faturação (charge_vv + charge_vv2 do Detailed Rentals), peso na receita total, % de contratos, RPD sem Via Verde.
- Danos cobrados (chargedamage): valor, peso na receita e por contrato fechado.
- Meses até 30/09/2026 fecham após a carga: o importador só atualiza Verdict/frota/avaliações nesses meses, salvo reabertura explícita.

## Customer Verdict
- Histórico: CSV autoUnion_responses_20250101-20261006 (2 228 respostas; 1 864 de Lisboa/Porto/Faro).
- Recolha: `coletor_verdict.js` num separador de https://dashboard.customer-verdict.com/autounion/export — pede o mesmo CSV do botão Download e guarda só nº de contrato, estação e notas (sem nomes, emails ou comentários).

## Atualizar o Excel de backup
`atualizar_backup_xml.py --backup Painel_ICONIQ_backup.xlsx --dados <export da base do dashboard> --de 2026-08 --ate 2026-09` acrescenta ao Base_Rentals os contratos recolhidos (coluna P = Via Verde), as Incremental Sales e a frota.

## Recolha semanal (sexta, 17:45)
1. Abrir https://iconiqfleet.wheelsys.io/ui/ no Chrome (sessão do Nuno). Se aparecer o login, parar e avisar.
2. Injetar `coletor_wheelsys.js` e correr `ICQ_RUN({de:<mês anterior>, ate:<mês atual>})`.
3. Esperar `window.ICQ.status === 'pronto'`; clicar no botão "Copiar dados ICONIQ".
4. Abrir o dashboard, expandir "Atualizar dados do WheelSys", clicar na caixa e colar (Ctrl+V). Confirmar a mensagem "Gravado: N meses".

## Validação (junho/2026, Portugal, contra o Excel)
Turnover 484 943,12 € · Net Rental 312 707,35 € · Rental Days 15 552 · Abertos 1 915 · Fechados 1 897 · Danos 26 041,40 € · Incremental Sales 45 133,44 € · iRPD 2,90 €. Tudo coincide.
Diferenças conhecidas do Excel: RNT-23624 está duplicado no Base_Rentals; a ocupação de Portugal no Excel (66,7 %) difere da recalculada (69,2 %), que segue o trabalho ISCTE.
