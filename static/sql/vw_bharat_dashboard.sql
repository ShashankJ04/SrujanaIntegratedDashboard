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


select  MM_RawMtPartNo 'RawMaterial',mt_name 'Material',
Batch ,date_format(ri_date, '%d-%m-%Y')  'InwardDt', 
RD_ACCEPTEDQTY 'inwardQty', storeQty as 'RM In Store',
round(COALESCE(GREATEST(ProdQty,0),0),2) 'RMGivenForProd' ,
round(COALESCE(GREATEST(ThRMForProduction,0),0),2) 'RMUsed(Theo)' ,
round(COALESCE(GREATEST((rmwithprod),0),0),2) as 'RM with Prod(Theo)' ,
round(COALESCE(GREATEST(pdscrap,0),0),2) 'ProdScrap',
round(COALESCE(GREATEST(SplitQty,0),0),2) 'RW with Slitting' ,
round(COALESCE(GREATEST(SlitingScrap,0),0),2) 'SlitingScrap' ,
round(COALESCE(GREATEST(JWRMGiven,0),0),2) 'JWRMGiven',
round(COALESCE(GREATEST(JWretqty,0),0),2) 'JWRetQty', 
round(COALESCE(GREATEST(JWcompkg,0),0),2) 'JWCompKg',
round(COALESCE(GREATEST(JWscarp,0),0),2) 'JWSrap',
round(COALESCE(GREATEST(jwRemQty,0),0),2) 'RM with JW Vendor' from 
(select inQ.rd_rmid rm, inQ.batch Batch,inQ.ri_date ri_date, 
inQ.RD_ACCEPTEDQTY , rmStore.Qty storeQty,
ProdQty,coalesce(ThRMForProduction,0)ThRMForProduction ,ProdQty-coalesce(ThRMForProduction,0)- coalesce(ProdQtyCorrection,0) rmwithprod ,
pdscrap -coalesce(PScrapCorrection,0) pdscrap,SplitQty,SlitingScrap-coalesce(SScrapCorrection,0) SlitingScrap,JWRMGiven,JWretqty, JWcompkg,JWscarp -coalesce(JWScrapCorrection,0) JWscarp ,jwRemQty
FROM 
(select rd_rmid , RD_BATCHNO batch ,ri_date, sum(RD_ACCEPTEDQTY  ) RD_ACCEPTEDQTY
from rm_inwarddetails
	 join rm_inwardmaster on rd_riid= ri_id 
     and RI_MOVEMENT='I' and RI_MOVEMENTTYPE=1
     left join materialmaster on mm_id = rd_rmid
     where RD_ACCEPTEDQTY>0
     group by RD_BATCHNO,ri_date,rd_rmid
       union
    select rmin.rd_rmid , rmin.RD_BATCHNO batch ,rmin.ri_date, rmin.RD_ACCEPTEDQTY   RD_ACCEPTEDQTY from 
    (SELECT * FROM rm_inwarddetails,rm_inwardmaster where  ri_id = rd_riid and rd_outwardid <>0 and RI_MOVEMENT='I' and RI_MOVEMENTTYPE=2) rmin,
     (SELECT * FROM rm_inwarddetails,rm_inwardmaster where  ri_id = rd_riid and RI_MOVEMENT='O' and RI_MOVEMENTTYPE=2) rmout
     where rmin.rd_rmid <>rmout.rd_rmid and rmin.RD_BATCHNO = rmout.RD_BATCHNO     
     )inQ
     left join (SELECT RD_BATCHNO batch, RD_RMID	,	
		round(SUM(CASE WHEN ri_movement = 'I' THEN rd_qty ELSE 0 END)
			- SUM(CASE WHEN ri_movement = 'O' THEN rd_qty ELSE 0 END), 2 )AS Qty
	FROM rm_inwarddetails , rm_inwardmaster
    where rd_riid=ri_id 
    group by RD_BATCHNO,rd_rmid) rmStore on rmStore.batch= inQ.batch and rmStore.rd_rmid = inQ.rd_rmid
     left join (select RD_BATCHNO batch,rd_rmid,
round(SUM(CASE WHEN ri_movement = 'O' THEN rd_qty ELSE 0 END)- SUM(CASE WHEN ri_movement = 'I' THEN rd_acceptedqty ELSE 0 END) ,2)AS ProdQty
from rm_inwarddetails
	 join rm_inwardmaster on rd_riid= ri_id 
     where RI_MOVEMENTTYPE = 3
     group by RD_BATCHNO,rd_rmid
     ) prod on prod.batch = inQ.batch and prod.rd_rmid = inQ.rd_rmid
     left join (select RD_BATCHNO batch, rd_rmid,coalesce(rd_qty,0) - coalesce(retqty,0) -coalesce(SlitingScrap,0) SplitQty, coalesce(SlitingScrap,0) SlitingScrap
     from rm_inwarddetails rd
	 join rm_inwardmaster on rd_riid= ri_id 
     left join ( select RD_OUTWARDID, sum(CASE WHEN ri_movement = 'I' THEN rd_acceptedqty ELSE 0 END) retqty
		from rm_inwarddetails, rm_inwardmaster where rd_riid= ri_id 
        and RI_MOVEMENTTYPE = 2 and  RI_MOVEMENT = 'I' group by RD_OUTWARDID
     )SplitRet on SplitRet.RD_OUTWARDID = rd.rd_id
     left join ( select RS_OUTWARDID,sum(rs_qty) SlitingScrap from rm_scrapdetails group by RS_OUTWARDID     
     )scrap on scrap.RS_OUTWARDID = rd.rd_id 
     where RI_MOVEMENTTYPE = 2 and  RI_MOVEMENT = 'O'
     ) Splitting on Splitting.batch = inQ.batch and Splitting.rd_rmid = inQ.rd_rmid
left join (  select pd_batchno batch, mm_id,round(coalesce(sum((PD_PRODQTY)/conVal),0),2)  ThRMForProduction ,  coalesce(sum(PD_SCRAPQTY),0) pdscrap from production_details
	left join scheduled_production on pd_psid = ps_id 
    left join comp_scrapdetails on sd_refno =pd_id and sd_src=1
	left join 
	(SELECT ct_id,CT_COMPID,mm_id ,((1 / ((MT_Density * MM_Thickness) * MM_StripWidth)) * ((1000 * CT_NO_OF_CAVITY) / CT_Pitch)) as conVal FROM components_tool
			inner join materialmaster on CT_RMID = MM_Id inner join materialtypemaster on MM_MTID = MT_Id where  CT_ActiveYN='Y' and CT_PPC='Y' and CT_PITCH > 0 
			and CT_NO_OF_CAVITY > 0)t on CT_COMPID= PS_PARENTCOMPID  and ct_id = PD_TOOLID
			group by  pd_batchno,mm_id)prodQ on prodQ.batch=inQ.batch and prodQ.mm_id = inQ.rd_rmid
	left join(select RD_BATCHNO batch,rd_rmid, rmgiven JWRMGiven ,sum(COALESCE(retRMqty,0)) JWretqty,sum(COALESCE(compkgqty,0))+ sum(COALESCE(sfRej,0)) JWcompkg,sum(COALESCE(scrapqty,0)) JWscarp, -- + sum(COALESCE(setupW,0))
        round((rmgiven-(sum(COALESCE(retRMqty,0))+ sum(COALESCE(compkgqty,0))  +sum(COALESCE(scrapqty,0)))),2) as jwRemQty from (   -- + sum(COALESCE(sfRej,0)) + sum(COALESCE(setupW,0))
		select rd_batchno, RD_RMID,RMGiven, retRMqty,compKGQty, scrapqty,sfRej,setupW
		from rm_inwarddetails rd
		join
		(select sum(rd_qty) RMGiven, RD_BATCHNO batch from rm_inwarddetails, rm_inwardmaster where rd_riid= ri_id and RI_MOVEMENT='O' and RI_MOVEMENTTYPE=4 group by RD_BATCHNO)r on r.batch = rd.rd_batchno
		left join  (select rd_id,RD_OUTWARDid, sum(RD_ACCEPTEDQTY) retRMqty from rm_inwarddetails,rm_inwardmaster where  ri_id = rd_riid and RI_MOVEMENT='I' and ri_movementtype=4 group by RD_OUTWARDID, rd_batchno,rd_id)ret on ret.RD_OUTWARDID= rd.rd_id 
		left join (select sum(cd_kgqty) compKGQty , cd_outwardid, sum(cr_qtykg) sfRej, sum(SD_QTYKG) setupW from comp_inwarddetails
			left join comp_rejectdetails on cr_cmid= cd_cmid
			left join comp_scrapdetails on sd_refno =cd_cmid and sd_src=4
			 where cd_src=4   group by cd_outwardid)comp on cd_outwardid=  ret.rd_id
		left join (SELECT rs_qty scrapqty,RS_OUTWARDID FROM rm_scrapdetails) scrap on scrap.RS_OUTWARDID=  ret.rd_id 
        ) t
		group by rd_batchno,rd_rmid) jwQty on jwQty.batch = inQ.batch   and jwQty.rd_rmid = inQ.rd_rmid    
	LEFT JOIN (
        SELECT
          TRIM(rc_batchno) AS rc_batchno,   rc_rmid,
          case when  rc_movementtype='P' then ROUND(SUM(COALESCE(rc_correction, 0)), 2) else 0 end AS PScrapCorrection,
          case when  rc_movementtype='S' then ROUND(SUM(COALESCE(rc_correction, 0)), 2) else 0 end AS SScrapCorrection,
          case when  rc_movementtype='J' then ROUND(SUM(COALESCE(rc_correction, 0)), 2) else 0 end AS JWScrapCorrection
        FROM rm_scrapcorrection       
        GROUP BY rc_batchno, rc_rmid,rc_movementtype
       ) scrapCorrections ON scrapCorrections.rc_batchno = inQ.batch  AND scrapCorrections.rc_rmid = inQ.rd_rmid
	LEFT JOIN (
        SELECT
          TRIM(rc_batchno) AS rc_batchno,   rc_rmid,
           ROUND(SUM(COALESCE(rc_correction, 0)), 2) ProdQtyCorrection
        FROM rm_prodcorrection       
        GROUP BY rc_batchno, rc_rmid
       ) prodCorrections ON prodCorrections.rc_batchno = inQ.batch  AND prodCorrections.rc_rmid = inQ.rd_rmid

        )t1 left join materialmaster on mm_id = t1.rm
        left join materialtypemaster on MM_MTID = MT_Id
        where storeQty >0 or rmwithprod >0 or jwRemQty>0 or splitQty>0 
        ;



        SELECT RH_ID rhId, RH_PLANTID rhPlantId, RH_MONTH rhMonth, RH_YEAR rhYear, RH_RMID rhRmId, RH_QTY rhQty, RH_MLID rhMlId, RH_WEEK rhWeek, RH_BATCHNO rhBatchNo,MM_RawMtPartNo rawMaterial,MT_Name mtType,ML_DESCRIPTION movement FROM rm_stockhistory

		left join materialmaster on mm_id = RH_RMID left join materialtypemaster on MM_mtId = MT_Id left join rm_movements on ML_ID = RH_MLID

		where RH_MONTH={month} and RH_YEAR={year} and RH_WEEK={week} order by RH_MLID