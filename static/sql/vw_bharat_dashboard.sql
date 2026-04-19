create or replace view vw_bharat_dashboard as 
SELECT 
    x.PART_NO AS 'PART NUMBER',
    x.PART_NAME AS 'PART NAME',
    x.QTY AS 'FEB',
    ROUND(x.QTY * 0.3) AS 'Buffer Stock',
    IFNULL(y_wip.csQty, 0) AS 'WIP',
    IFNULL(y_fg.csQty, 0) AS 'FG',
    (IFNULL(y_wip.csQty, 0) + IFNULL(y_fg.csQty, 0)) AS 'Total Stock',
    ROUND(x.QTY * 1.3) - (IFNULL(y_wip.csQty, 0) + IFNULL(y_fg.csQty, 0)) AS 'Production Pending',
    IFNULL(z.pdProdQty, 0) AS 'Produced Qty',
    (ROUND(x.QTY * 1.3) - (IFNULL(y_wip.csQty, 0) + IFNULL(y_fg.csQty, 0))) - IFNULL(z.pdProdQty, 0) AS 'Balance Production Quantity'
FROM (
    -- Subquery x: Sales Demand
    SELECT PART_NAME, PART_NO, SUM(QTY) QTY FROM (
        SELECT PART_NAME, PART_NO, SUM(QTY) AS qty FROM sales_order 
        WHERE EXTRACT(YEAR_MONTH from DLV_DATE) =  EXTRACT(YEAR_MONTH from current_date) 
        AND CATEGORY_ID = 1 AND SO_TYPE_ID IN (1,2) AND STATUS_ID in (1,7)
        GROUP BY PART_NAME, PART_NO
        UNION ALL
        SELECT b.PART_NAME, b.PART_NO, SUM(a.QTY * b.QTY) AS qty 
        FROM sales_order a 
        JOIN bom_lin_item b ON b.bom_id IN (SELECT c.bom_id FROM bom c WHERE c.bom_no = a.bom_no AND c.is_latest_version = 'Y')
        WHERE EXTRACT(YEAR_MONTH from a.DLV_DATE) =  EXTRACT(YEAR_MONTH from current_date) 
        AND a.CATEGORY_ID = 2 AND a.SO_TYPE_ID IN (1,2) AND a.STATUS_ID in (1,7) AND category_code = 'SS'
        GROUP BY b.PART_NAME, b.PART_NO
    ) a GROUP BY PART_NAME, PART_NO
) x
LEFT JOIN (
    -- Subquery y_fg: Finished Goods (Stage 6)
    SELECT c.CO_PARTNO AS PART_NO, SUM(a.csQty) AS csQty 
    FROM (
        SELECT CH_CompId csCompId, CH_Qty csQty FROM comp_stockhistory 
        WHERE CH_PlantId = 3 AND CH_Month = EXTRACT(MONTh from current_date) - 1 AND CH_Year = EXTRACT(YEAR from date_add(current_date,Interval -1 Month)) AND CH_StageId = 6
        UNION ALL 
        SELECT CT_COmpId, SUM(CASE WHEN CT_Movement='I' THEN CT_QTy ELSE -CT_QTy END) 
        FROM comp_transaction WHERE CT_PlantId = 3 AND CT_Date = last_day(date_add(current_date,Interval -1 Month)) AND (CT_Nextstage=6 OR CT_Opstage=6)
        GROUP BY CT_CompId
    ) a JOIN components c ON a.csCompId = c.CO_id WHERE c.CO_ACTIVEYN = 'Y'
    GROUP BY c.CO_PARTNO
) y_fg ON x.PART_NO = y_fg.PART_NO
LEFT JOIN (
    -- Subquery y_wip: Work In Progress (Stages other than 6)
    SELECT c.CO_PARTNO AS PART_NO, SUM(a.csQty) AS csQty 
    FROM (
        SELECT CH_CompId csCompId, CH_Qty csQty FROM comp_stockhistory 
        WHERE CH_PlantId = 3 AND CH_Month = EXTRACT(MONTh from current_date) - 1 AND CH_Year = EXTRACT(YEAR from date_add(current_date,Interval -1 Month)) AND CH_StageId != 6
        UNION ALL 
        SELECT CT_COmpId, SUM(CASE WHEN CT_Movement='I' THEN CT_QTy ELSE -CT_QTy END) 
        FROM comp_transaction WHERE CT_PlantId = 3 AND CT_Date = last_day(date_add(current_date,Interval -1 Month)) AND (CT_Nextstage != 6 OR CT_Opstage != 6)
        GROUP BY CT_CompId
    ) a JOIN components c ON a.csCompId = c.CO_id WHERE c.CO_ACTIVEYN = 'Y'
    GROUP BY c.CO_PARTNO
) y_wip ON x.PART_NO = y_wip.PART_NO
LEFT JOIN (
    -- Subquery z: Supervisor Production
    SELECT CO_partNo AS PART_NO, SUM(PD_PRODQTY) pdProdQty 
    FROM scheduled_production
    INNER JOIN production_details ON PS_ID = PD_PSID
    INNER JOIN schedule_master ON SM_Id = PS_SMID
    INNER JOIN components ON CO_Id = PS_ParentCompId
    WHERE EXTRACT(YEAR_MONTH from PD_DATE) = EXTRACT(YEAR_MONTH from current_date) AND SM_Status='S' AND PS_plantId=3
    GROUP BY CO_partNo
) z ON x.PART_NO = z.PART_NO;