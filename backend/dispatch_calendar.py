"""Dispatch Calendar — Monthly Order + Consolidated Stock merge for Hub section."""

from __future__ import annotations

import calendar
import logging
import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from . import reports_store
from .db import fetch_all

MONTHLY_ORDER_REPORT_ID = "dd2e5dd7-d47e-43bb-8a5c-b838c5bd88c3"
STOCK_REPORT_ID = "5c7c5e6c-6f88-4f6e-9b69-bc0f63c8a663"
DISPATCH_BETWEEN_DATES_REPORT_ID = "a491c9dc-b8a5-4d9c-92f2-073926e837e0"

logger = logging.getLogger(__name__)

FG_STOCK_COL = "FG (Stock)"
PART_NO_COL = "Part No"
NO_OF_OPERATIONS_COL = "No of Operations"
TOTAL_QTY_COL = "Total Scheduled Qty"
TOTAL_DISPATCHED_QTY_COL = "Total Dispatched Qty"
DISPATCHED_PCT_COL = "Dispatched %"
_DISPATCH_CALENDAR_QUERY_CACHE: Optional[Dict[str, str]] = None

MONTHLY_ORDER_QUERY_TEMPLATE = """SELECT
  t.partno    AS 'Part No',
  t.no_of_operations AS 'No of Operations',
  t.total_qty AS 'Total Scheduled Qty',
  t.day_1     AS 'day 1',
  t.day_2     AS 'day 2',
  t.day_3     AS 'day 3',
  t.day_4     AS 'day 4',
  t.day_5     AS 'day 5',
  t.day_6     AS 'day 6',
  t.day_7     AS 'day 7',
  t.day_8     AS 'day 8',
  t.day_9     AS 'day 9',
  t.day_10    AS 'day 10',
  t.day_11    AS 'day 11',
  t.day_12    AS 'day 12',
  t.day_13    AS 'day 13',
  t.day_14    AS 'day 14',
  t.day_15    AS 'day 15',
  t.day_16    AS 'day 16',
  t.day_17    AS 'day 17',
  t.day_18    AS 'day 18',
  t.day_19    AS 'day 19',
  t.day_20    AS 'day 20',
  t.day_21    AS 'day 21',
  t.day_22    AS 'day 22',
  t.day_23    AS 'day 23',
  t.day_24    AS 'day 24',
  t.day_25    AS 'day 25',
  t.day_26    AS 'day 26',
  t.day_27    AS 'day 27',
  t.day_28    AS 'day 28',
  t.day_29    AS 'day 29',
  t.day_30    AS 'day 30',
  t.day_31    AS 'day 31'
FROM (
  SELECT
    0 AS sort_order,
    'Grand Total' AS partno,
    NULL AS no_of_operations,
    SUM(sc.CS_QTY) AS total_qty,
    SUM(CASE WHEN DAY(sc.CS_DATE) = 1 THEN sc.CS_QTY ELSE 0 END) AS day_1,
    SUM(CASE WHEN DAY(sc.CS_DATE) = 2 THEN sc.CS_QTY ELSE 0 END) AS day_2,
    SUM(CASE WHEN DAY(sc.CS_DATE) = 3 THEN sc.CS_QTY ELSE 0 END) AS day_3,
    SUM(CASE WHEN DAY(sc.CS_DATE) = 4 THEN sc.CS_QTY ELSE 0 END) AS day_4,
    SUM(CASE WHEN DAY(sc.CS_DATE) = 5 THEN sc.CS_QTY ELSE 0 END) AS day_5,
    SUM(CASE WHEN DAY(sc.CS_DATE) = 6 THEN sc.CS_QTY ELSE 0 END) AS day_6,
    SUM(CASE WHEN DAY(sc.CS_DATE) = 7 THEN sc.CS_QTY ELSE 0 END) AS day_7,
    SUM(CASE WHEN DAY(sc.CS_DATE) = 8 THEN sc.CS_QTY ELSE 0 END) AS day_8,
    SUM(CASE WHEN DAY(sc.CS_DATE) = 9 THEN sc.CS_QTY ELSE 0 END) AS day_9,
    SUM(CASE WHEN DAY(sc.CS_DATE) = 10 THEN sc.CS_QTY ELSE 0 END) AS day_10,
    SUM(CASE WHEN DAY(sc.CS_DATE) = 11 THEN sc.CS_QTY ELSE 0 END) AS day_11,
    SUM(CASE WHEN DAY(sc.CS_DATE) = 12 THEN sc.CS_QTY ELSE 0 END) AS day_12,
    SUM(CASE WHEN DAY(sc.CS_DATE) = 13 THEN sc.CS_QTY ELSE 0 END) AS day_13,
    SUM(CASE WHEN DAY(sc.CS_DATE) = 14 THEN sc.CS_QTY ELSE 0 END) AS day_14,
    SUM(CASE WHEN DAY(sc.CS_DATE) = 15 THEN sc.CS_QTY ELSE 0 END) AS day_15,
    SUM(CASE WHEN DAY(sc.CS_DATE) = 16 THEN sc.CS_QTY ELSE 0 END) AS day_16,
    SUM(CASE WHEN DAY(sc.CS_DATE) = 17 THEN sc.CS_QTY ELSE 0 END) AS day_17,
    SUM(CASE WHEN DAY(sc.CS_DATE) = 18 THEN sc.CS_QTY ELSE 0 END) AS day_18,
    SUM(CASE WHEN DAY(sc.CS_DATE) = 19 THEN sc.CS_QTY ELSE 0 END) AS day_19,
    SUM(CASE WHEN DAY(sc.CS_DATE) = 20 THEN sc.CS_QTY ELSE 0 END) AS day_20,
    SUM(CASE WHEN DAY(sc.CS_DATE) = 21 THEN sc.CS_QTY ELSE 0 END) AS day_21,
    SUM(CASE WHEN DAY(sc.CS_DATE) = 22 THEN sc.CS_QTY ELSE 0 END) AS day_22,
    SUM(CASE WHEN DAY(sc.CS_DATE) = 23 THEN sc.CS_QTY ELSE 0 END) AS day_23,
    SUM(CASE WHEN DAY(sc.CS_DATE) = 24 THEN sc.CS_QTY ELSE 0 END) AS day_24,
    SUM(CASE WHEN DAY(sc.CS_DATE) = 25 THEN sc.CS_QTY ELSE 0 END) AS day_25,
    SUM(CASE WHEN DAY(sc.CS_DATE) = 26 THEN sc.CS_QTY ELSE 0 END) AS day_26,
    SUM(CASE WHEN DAY(sc.CS_DATE) = 27 THEN sc.CS_QTY ELSE 0 END) AS day_27,
    SUM(CASE WHEN DAY(sc.CS_DATE) = 28 THEN sc.CS_QTY ELSE 0 END) AS day_28,
    SUM(CASE WHEN DAY(sc.CS_DATE) = 29 THEN sc.CS_QTY ELSE 0 END) AS day_29,
    SUM(CASE WHEN DAY(sc.CS_DATE) = 30 THEN sc.CS_QTY ELSE 0 END) AS day_30,
    SUM(CASE WHEN DAY(sc.CS_DATE) = 31 THEN sc.CS_QTY ELSE 0 END) AS day_31
  FROM schedule_master sm
  JOIN schedule_details sd ON sm.SM_ID = sd.SC_SMID
  JOIN scheduled_customer sc ON sd.SC_ID = sc.CS_SCID
  JOIN components c ON sd.SC_COMPID = c.CO_ID
  WHERE sm.SM_MONTH = {month}
    AND sm.SM_YEAR = {year}
    AND sc.CS_SCHEDULESTATE IN (1, 2)

  UNION ALL

  SELECT
    1 AS sort_order,
    c.CO_PARTNO AS partno,
    MAX(c.CO_NoOfOp) AS no_of_operations,
    SUM(sc.CS_QTY) AS total_qty,
    SUM(CASE WHEN DAY(sc.CS_DATE) = 1 THEN sc.CS_QTY ELSE 0 END) AS day_1,
    SUM(CASE WHEN DAY(sc.CS_DATE) = 2 THEN sc.CS_QTY ELSE 0 END) AS day_2,
    SUM(CASE WHEN DAY(sc.CS_DATE) = 3 THEN sc.CS_QTY ELSE 0 END) AS day_3,
    SUM(CASE WHEN DAY(sc.CS_DATE) = 4 THEN sc.CS_QTY ELSE 0 END) AS day_4,
    SUM(CASE WHEN DAY(sc.CS_DATE) = 5 THEN sc.CS_QTY ELSE 0 END) AS day_5,
    SUM(CASE WHEN DAY(sc.CS_DATE) = 6 THEN sc.CS_QTY ELSE 0 END) AS day_6,
    SUM(CASE WHEN DAY(sc.CS_DATE) = 7 THEN sc.CS_QTY ELSE 0 END) AS day_7,
    SUM(CASE WHEN DAY(sc.CS_DATE) = 8 THEN sc.CS_QTY ELSE 0 END) AS day_8,
    SUM(CASE WHEN DAY(sc.CS_DATE) = 9 THEN sc.CS_QTY ELSE 0 END) AS day_9,
    SUM(CASE WHEN DAY(sc.CS_DATE) = 10 THEN sc.CS_QTY ELSE 0 END) AS day_10,
    SUM(CASE WHEN DAY(sc.CS_DATE) = 11 THEN sc.CS_QTY ELSE 0 END) AS day_11,
    SUM(CASE WHEN DAY(sc.CS_DATE) = 12 THEN sc.CS_QTY ELSE 0 END) AS day_12,
    SUM(CASE WHEN DAY(sc.CS_DATE) = 13 THEN sc.CS_QTY ELSE 0 END) AS day_13,
    SUM(CASE WHEN DAY(sc.CS_DATE) = 14 THEN sc.CS_QTY ELSE 0 END) AS day_14,
    SUM(CASE WHEN DAY(sc.CS_DATE) = 15 THEN sc.CS_QTY ELSE 0 END) AS day_15,
    SUM(CASE WHEN DAY(sc.CS_DATE) = 16 THEN sc.CS_QTY ELSE 0 END) AS day_16,
    SUM(CASE WHEN DAY(sc.CS_DATE) = 17 THEN sc.CS_QTY ELSE 0 END) AS day_17,
    SUM(CASE WHEN DAY(sc.CS_DATE) = 18 THEN sc.CS_QTY ELSE 0 END) AS day_18,
    SUM(CASE WHEN DAY(sc.CS_DATE) = 19 THEN sc.CS_QTY ELSE 0 END) AS day_19,
    SUM(CASE WHEN DAY(sc.CS_DATE) = 20 THEN sc.CS_QTY ELSE 0 END) AS day_20,
    SUM(CASE WHEN DAY(sc.CS_DATE) = 21 THEN sc.CS_QTY ELSE 0 END) AS day_21,
    SUM(CASE WHEN DAY(sc.CS_DATE) = 22 THEN sc.CS_QTY ELSE 0 END) AS day_22,
    SUM(CASE WHEN DAY(sc.CS_DATE) = 23 THEN sc.CS_QTY ELSE 0 END) AS day_23,
    SUM(CASE WHEN DAY(sc.CS_DATE) = 24 THEN sc.CS_QTY ELSE 0 END) AS day_24,
    SUM(CASE WHEN DAY(sc.CS_DATE) = 25 THEN sc.CS_QTY ELSE 0 END) AS day_25,
    SUM(CASE WHEN DAY(sc.CS_DATE) = 26 THEN sc.CS_QTY ELSE 0 END) AS day_26,
    SUM(CASE WHEN DAY(sc.CS_DATE) = 27 THEN sc.CS_QTY ELSE 0 END) AS day_27,
    SUM(CASE WHEN DAY(sc.CS_DATE) = 28 THEN sc.CS_QTY ELSE 0 END) AS day_28,
    SUM(CASE WHEN DAY(sc.CS_DATE) = 29 THEN sc.CS_QTY ELSE 0 END) AS day_29,
    SUM(CASE WHEN DAY(sc.CS_DATE) = 30 THEN sc.CS_QTY ELSE 0 END) AS day_30,
    SUM(CASE WHEN DAY(sc.CS_DATE) = 31 THEN sc.CS_QTY ELSE 0 END) AS day_31
  FROM schedule_master sm
  JOIN schedule_details sd ON sm.SM_ID = sd.SC_SMID
  JOIN scheduled_customer sc ON sd.SC_ID = sc.CS_SCID
  JOIN components c ON sd.SC_COMPID = c.CO_ID
  WHERE sm.SM_MONTH = {month}
    AND sm.SM_YEAR = {year}
    AND sc.CS_SCHEDULESTATE IN (1, 2)
  GROUP BY c.CO_PARTNO
) t
ORDER BY t.sort_order, t.partno;"""

STOCK_QUERY_TEMPLATE = """SELECT
    AP.co_partno AS 'Part No',AP.CO_PARTNAME,AP.CO_WEIGHT,AP.MT_Name,

    COALESCE(S.stk_1st_Forming, 0) AS '1st Forming (Stock)',
    COALESCE(S.stk_Electroplating, 0) AS 'Electroplating (Stock)',
    COALESCE(S.stk_Soapwash, 0) AS 'Soapwash (Stock)',
    COALESCE(S.stk_Tapping, 0) AS 'Tapping (Stock)',
    COALESCE(S.stk_FG, 0) AS 'FG (Stock)',
    COALESCE(S.stk_2nd_Forming, 0) AS '2nd Forming (Stock)',
    COALESCE(S.stk_3rd_Forming, 0) AS '3rd Forming (Stock)',
    COALESCE(S.stk_Etching, 0) AS 'Etching (Stock)',
    COALESCE(S.stk_Deburring, 0) AS 'Deburring (Stock)',
    COALESCE(S.stk_Laser_Welding, 0) AS 'Laser Welding (Stock)',
    COALESCE(S.stk_Ultrasonic_Cleaning, 0) AS 'Ultrasonic Cleaning (Stock)',
    COALESCE(S.stk_Arcor_Coating, 0) AS 'Arcor Coating (Stock)',
    COALESCE(S.stk_Riveting, 0) AS 'Riveting (Stock)',
    COALESCE(S.stk_Brazing, 0) AS 'Brazing (Stock)',
    COALESCE(S.stk_Heat_Sealing, 0) AS 'Heat Sealing (Stock)',
    COALESCE(S.stk_Dimpling, 0) AS 'Dimpling (Stock)',

    COALESCE(B.bal_1st_Forming, 0) AS '1st Forming (With Supplier)',
    COALESCE(B.bal_Electroplating, 0) AS 'Electroplating (With Supplier)',
    COALESCE(B.bal_Soapwash, 0) AS 'Soapwash (With Supplier)',
    COALESCE(B.bal_Tapping, 0) AS 'Tapping (With Supplier)',
    COALESCE(B.bal_FG, 0) AS 'FG (With Supplier)',
    COALESCE(B.bal_2nd_Forming, 0) AS '2nd Forming (With Supplier)',
    COALESCE(B.bal_3rd_Forming, 0) AS '3rd Forming (With Supplier)',
    COALESCE(B.bal_Etching, 0) AS 'Etching (With Supplier)',
    COALESCE(B.bal_Deburring, 0) AS 'Deburring (With Supplier)',
    COALESCE(B.bal_Laser_Welding, 0) AS 'Laser Welding (With Supplier)',
    COALESCE(B.bal_Ultrasonic_Cleaning, 0) AS 'Ultrasonic Cleaning (With Supplier)',
    COALESCE(B.bal_Arcor_Coating, 0) AS 'Arcor Coating (With Supplier)',
    COALESCE(B.bal_Riveting, 0) AS 'Riveting (With Supplier)',
    COALESCE(B.bal_Brazing, 0) AS 'Brazing (With Supplier)',
    COALESCE(B.bal_Heat_Sealing, 0) AS 'Heat Sealing (With Supplier)',
    COALESCE(B.bal_Dimpling, 0) AS 'Dimpling (With Supplier)',

    COALESCE(Q.qa_supplier, 0) AS 'QA Pending from Supplier',
    COALESCE(Q.qa_production, 0) AS 'QA Pending from Production',
    COALESCE(Q.qa_disposition, 0) AS 'QA Disposition',
    COALESCE(Q.rework_pending, 0) AS 'Rework Pending'
FROM (
    SELECT DISTINCT co_partno ,CO_PARTNAME,CO_WEIGHT,MT_Name
    FROM components inner join materialtypemaster on MT_Id = CO_MATERIALTYPEID
    WHERE co_partno IS NOT NULL and CO_ACTIVEYN ='Y' and co_id=CO_PARENTID
) AP
LEFT JOIN (
    SELECT
    co_partno AS 'PartNo',
    CO_PARTNAME,
    SUM(max_forming_1) AS stk_1st_Forming,
    SUM(max_electro) AS stk_Electroplating,
    SUM(max_soap) AS stk_Soapwash,
    SUM(max_tapping) AS stk_Tapping,
    SUM(max_fg) AS stk_FG,
    SUM(max_forming_2) AS stk_2nd_Forming,
    SUM(max_forming_3) AS stk_3rd_Forming,
    SUM(max_etching) AS stk_Etching,
    SUM(max_deburring) AS stk_Deburring,
    SUM(max_laser) AS stk_Laser_Welding,
    SUM(max_ultrasonic) AS stk_Ultrasonic_Cleaning,
    SUM(max_arcor) AS stk_Arcor_Coating,
    SUM(max_riveting) AS stk_Riveting,
    SUM(max_brazing) AS stk_Brazing,
    SUM(max_sealing) AS stk_Heat_Sealing,
    SUM(max_dimpling) AS stk_Dimpling
FROM (
    SELECT
        co_partno,
        CO_PARTNAME,
        cs_plantid,
        MAX(CASE WHEN os_id = 2 THEN cs_qty ELSE 0 END) AS max_forming_1,
        MAX(CASE WHEN os_id = 3 THEN cs_qty ELSE 0 END) AS max_electro,
        MAX(CASE WHEN os_id = 4 THEN cs_qty ELSE 0 END) AS max_soap,
        MAX(CASE WHEN os_id = 5 THEN cs_qty ELSE 0 END) AS max_tapping,
        MAX(CASE WHEN os_id = 6 THEN cs_qty ELSE 0 END) AS max_fg,
        MAX(CASE WHEN os_id = 7 THEN cs_qty ELSE 0 END) AS max_forming_2,
        MAX(CASE WHEN os_id = 8 THEN cs_qty ELSE 0 END) AS max_forming_3,
        MAX(CASE WHEN os_id = 9 THEN cs_qty ELSE 0 END) AS max_etching,
        MAX(CASE WHEN os_id = 10 THEN cs_qty ELSE 0 END) AS max_deburring,
        MAX(CASE WHEN os_id = 12 THEN cs_qty ELSE 0 END) AS max_laser,
        MAX(CASE WHEN os_id = 13 THEN cs_qty ELSE 0 END) AS max_ultrasonic,
        MAX(CASE WHEN os_id = 14 THEN cs_qty ELSE 0 END) AS max_arcor,
        MAX(CASE WHEN os_id = 15 THEN cs_qty ELSE 0 END) AS max_riveting,
        MAX(CASE WHEN os_id = 16 THEN cs_qty ELSE 0 END) AS max_brazing,
        MAX(CASE WHEN os_id = 17 THEN cs_qty ELSE 0 END) AS max_sealing,
        MAX(CASE WHEN os_id = 18 THEN cs_qty ELSE 0 END) AS max_dimpling
    FROM comp_stock
    LEFT JOIN comp_opstages ON CS_STAGEID = os_id
    LEFT JOIN components ON CS_COMPID = co_id
    WHERE cs_qty > 0
    and cs_plantid in (1,2)
    GROUP BY co_partno, CO_PARTNAME,cs_plantid
) t
GROUP BY co_partno,CO_PARTNAME
) S ON AP.co_partno = S.PartNo and AP.CO_PARTNAME = S.CO_PARTNAME
LEFT JOIN (
    SELECT
        co_partno AS PartNo,CO_PARTNAME,
        SUM(QAFromSup_pending) AS qa_supplier,
        SUM(ProdQA_pending)    AS qa_production,
        SUM(qa_disp_pending)   AS qa_disposition,
        SUM(rw_pending)        AS rework_pending
    FROM (
        SELECT CD_COMPID AS comp_id, COALESCE(SUM(QD_OFFEREDQTY), 0) AS QAFromSup_pending, 0 as ProdQA_pending, 0 AS qa_disp_pending, 0 AS rw_pending
        FROM comp_inwardmaster
        INNER JOIN comp_inwarddetails ON CM_ID = CD_CMID
        INNER JOIN qa_details ON QD_CMID = CM_ID
        WHERE QD_STATUS = 'P' AND QD_CRID = 0
        GROUP BY CD_COMPID
        UNION ALL
        SELECT PS_PARENTCOMPID AS comp_id, 0 as QASup_pending, COALESCE(SUM(QD_OFFEREDQTY), 0) AS ProdQA_pending, 0 AS qa_disp_pending, 0 AS rw_pending
        FROM scheduled_production
        INNER JOIN production_details ON ps_id = pd_psid
        INNER JOIN qa_details ON pd_id = qd_pdid
        WHERE QD_STATUS = 'P' AND QD_CRID = 0
        GROUP BY PS_PARENTCOMPID
        UNION ALL
        SELECT CR_COMPID AS comp_id, 0 AS qa_pending, 0 as ProdQA_pending, COALESCE(SUM(CR_QTY), 0) AS qa_disp_pending, 0 AS rw_pending
        FROM comp_rejectdetails
        WHERE CR_STATUS = 'P'
        GROUP BY CR_COMPID
        UNION ALL
        SELECT CR_COMPID AS comp_id, 0 AS qa_pending, 0 as ProdQA_pending, 0 AS qa_disp_pending, COALESCE(SUM(CR_QTY) - COALESCE(sum(t2.rdQty), 0), 0) AS rw_pending
        FROM comp_rejectdetails
        LEFT JOIN (
            SELECT RD_CRID AS crId, SUM(RD_QTY) AS rdQty
            FROM comp_rejinvdetails
            INNER JOIN comp_rejinvmaster ON RD_RJID = RJ_ID
            INNER JOIN comp_rejectdetails ON CR_ID = RD_CRID
            WHERE RJ_MOVEMENT = 'O' AND CR_STATUS = 'R'
            GROUP BY RD_CRID
        ) t2 ON t2.crId = CR_ID
        WHERE CR_STATUS = 'R'
        GROUP BY CR_COMPID
    ) combined
    LEFT JOIN components ON co_id = comp_id
    GROUP BY co_partno ,CO_PARTNAME
) Q ON AP.co_partno = Q.PartNo and AP.CO_PARTNAME=Q.CO_PARTNAME
LEFT JOIN (
    SELECT
        co_partno AS PartNo, CO_PARTNAME,
        MAX(CASE WHEN cd_opstage = 2  THEN compbalance END) AS bal_1st_Forming,
        MAX(CASE WHEN cd_opstage = 3  THEN compbalance END) AS bal_Electroplating,
        MAX(CASE WHEN cd_opstage = 4  THEN compbalance END) AS bal_Soapwash,
        MAX(CASE WHEN cd_opstage = 5  THEN compbalance END) AS bal_Tapping,
        MAX(CASE WHEN cd_opstage = 6  THEN compbalance END) AS bal_FG,
        MAX(CASE WHEN cd_opstage = 7  THEN compbalance END) AS bal_2nd_Forming,
        MAX(CASE WHEN cd_opstage = 8  THEN compbalance END) AS bal_3rd_Forming,
        MAX(CASE WHEN cd_opstage = 9  THEN compbalance END) AS bal_Etching,
        MAX(CASE WHEN cd_opstage = 10 THEN compbalance END) AS bal_Deburring,
        MAX(CASE WHEN cd_opstage = 12 THEN compbalance END) AS bal_Laser_Welding,
        MAX(CASE WHEN cd_opstage = 13 THEN compbalance END) AS bal_Ultrasonic_Cleaning,
        MAX(CASE WHEN cd_opstage = 14 THEN compbalance END) AS bal_Arcor_Coating,
        MAX(CASE WHEN cd_opstage = 15 THEN compbalance END) AS bal_Riveting,
        MAX(CASE WHEN cd_opstage = 16 THEN compbalance END) AS bal_Brazing,
        MAX(CASE WHEN cd_opstage = 17 THEN compbalance END) AS bal_Heat_Sealing,
        MAX(CASE WHEN cd_opstage = 18 THEN compbalance END) AS bal_Dimpling
    FROM (
        SELECT co_id, CO_PARTNO,CO_PARTNAME, cd_opstage,
               COALESCE(SUM(CASE WHEN cm_movement = 'O' THEN cd_qty WHEN cm_movement = 'I' THEN -cd_qty ELSE 0 END), 0) - COALESCE(sum(sd_qty), 0) AS compbalance
        FROM comp_inwardmaster
        INNER JOIN comp_inwarddetails ON cm_id = cd_cmid
        LEFT JOIN comp_opstages ON cd_opstage = os_id
        LEFT JOIN components ON CD_COMPID = co_id AND CO_ACTIVEYN = 'Y'
        LEFT JOIN comp_scrapdetails ON sd_source='S' AND sd_src=3 AND sd_refno=CD_CMID AND sd_compid = cd_compid AND SD_OPSTAGE = cd_opstage
        WHERE cm_id = cd_cmid and co_id is not null and CD_SOURCE='C'
        GROUP BY cd_compid, cd_opstage, co_id, CO_PARTNO,CO_PARTNAME
    ) t3
    WHERE compbalance > 0
    GROUP BY co_partno,CO_PARTNAME
) B ON AP.co_partno = B.PartNo and Ap.CO_PARTNAME = B.CO_PARTNAME
WHERE S.PartNo IS NOT NULL
   OR Q.PartNo IS NOT NULL
   OR B.PartNo IS NOT NULL
 ORDER BY AP.co_partno;"""

DISPATCH_BETWEEN_DATES_QUERY_TEMPLATE = """SELECT
  CU_Name AS Customer,
  CO_partNo AS 'Part No',
  CO_partName AS 'Part Name',
  CS_PLANTID AS 'Unit',
  DATE_FORMAT(CS_DATE, '%d-%m-%Y') AS 'Requested Date',
  CS_QTY AS 'Requested Qty(Nos)',
  SD_LOTSIZE AS 'Dispatched Qty(Nos)',
  SD_INVOICE AS 'Invoice Number',
  DATE_FORMAT(SD_DISPATCHDATE, '%d-%m-%Y') AS 'Invoice Date',
DS_NAME as 'Status'
FROM scheduled_customerdispatch
INNER JOIN scheduled_customer ON SD_CSID = CS_Id
INNER JOIN customer ON CU_Id = CS_CUSTID
INNER JOIN schedule_details ON SC_Id = CS_SCID
INNER JOIN components ON CO_Id = SC_COMPID
INNER JOIN dispatch_status ON DS_Id = SD_Status
WHERE SD_Status = 7
 AND CS_DATE BETWEEN STR_TO_DATE({fromDate}, '%d-%m-%Y')
AND STR_TO_DATE({toDate}, '%d-%m-%Y');"""


def _normalize_part_key(part_no: Any) -> str:
    return str(part_no or "").strip().lower()


def _to_float(v: Any) -> float:
    if v is None:
        return 0.0
    if isinstance(v, bool):
        return float(v)
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, Decimal):
        return float(v)
    s = str(v).strip().replace(",", "")
    if not s:
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def _load_dispatch_calendar_query_templates() -> Dict[str, str]:
    """Return required report SQL templates for dispatch calendar."""
    global _DISPATCH_CALENDAR_QUERY_CACHE
    if _DISPATCH_CALENDAR_QUERY_CACHE is not None:
        return _DISPATCH_CALENDAR_QUERY_CACHE

    _DISPATCH_CALENDAR_QUERY_CACHE = {
        MONTHLY_ORDER_REPORT_ID: MONTHLY_ORDER_QUERY_TEMPLATE,
        STOCK_REPORT_ID: STOCK_QUERY_TEMPLATE,
        DISPATCH_BETWEEN_DATES_REPORT_ID: DISPATCH_BETWEEN_DATES_QUERY_TEMPLATE,
    }
    return _DISPATCH_CALENDAR_QUERY_CACHE


def _serialize_cell(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (int, float, str, bool)):
        return v
    if hasattr(v, "isoformat"):
        return str(v)
    return v


def _serialize_row(row: Dict[str, Any]) -> Dict[str, Any]:
    return {k: _serialize_cell(v) for k, v in row.items()}


def _fg_wip_from_stock_row(stock_row: Dict[str, Any]) -> Tuple[float, float]:
    fg = _to_float(stock_row.get(FG_STOCK_COL))
    wip = 0.0
    for k, v in stock_row.items():
        key = str(k or "").strip()
        if not key:
            continue
        key_l = key.lower()
        # Include all numeric process-stage columns in WIP (not just "(Stock)" suffix).
        if key == FG_STOCK_COL or key_l in {"part no", "partno", "co_partno", "part name", "co_weight"}:
            continue
        if "part" in key_l and ("no" in key_l or "name" in key_l):
            continue
        qty = _to_float(v)
        if qty != 0.0:
            wip += qty
    return fg, wip


def _build_stock_index(stock_rows: List[Dict[str, Any]]) -> Dict[str, Tuple[float, float]]:
    out: Dict[str, Tuple[float, float]] = {}
    for sr in stock_rows:
        key = _normalize_part_key(_mo_part_no_raw(sr))
        if not key:
            continue
        out[key] = _fg_wip_from_stock_row(sr)
    return out


def _is_grand_total_row(row: Dict[str, Any]) -> bool:
    return _normalize_part_key(_mo_part_no_raw(row)) == "grand total"


def _day_column_key(day: int) -> str:
    return f"day {day}"


REQUESTED_DATE_COL = "Requested Date"
DISPATCHED_QTY_COL = "Dispatched Qty(Nos)"


def _first_matching_key(row: Dict[str, Any], candidates: Tuple[str, ...]) -> Any:
    """Resolve a column value when drivers may vary casing/aliases (PyMySQL dict keys)."""
    for name in candidates:
        if name in row:
            return row[name]
    lower_index = {str(k).lower(): k for k in row.keys()}
    for name in candidates:
        lk = name.lower()
        if lk in lower_index:
            return row[lower_index[lk]]
    return None


def _mo_part_no_raw(row: Dict[str, Any]) -> Any:
    """Resolve part number from Monthly Order / stock rows (driver-specific column names)."""
    return _first_matching_key(
        row,
        (
            PART_NO_COL,
            "Part No",
            "part no",
            "CO_PARTNO",
            "CO_partNo",
            "partno",
            "PARTNO",
        ),
    )


def _parse_calendar_day_value(
    raw: Any, month: int, year: int, days_in_month: int
) -> Optional[int]:
    """Calendar day-of-month in `month`/`year`, or None (DD-MM-YYYY, ISO, date/datetime)."""
    if raw is None:
        return None
    if isinstance(raw, (date, datetime)):
        dt = raw if isinstance(raw, date) else raw.date()
        if dt.month != month or dt.year != year:
            return None
        if 1 <= dt.day <= days_in_month:
            return int(dt.day)
        return None
    text = str(raw).strip()
    if not text:
        return None
    # ISO date or datetime prefix (e.g. JSON / str(datetime))
    iso_m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", text)
    if iso_m:
        y, mo, d_d = int(iso_m.group(1)), int(iso_m.group(2)), int(iso_m.group(3))
        if mo == month and y == year and 1 <= d_d <= days_in_month:
            return d_d
        return None
    # DD-MM-YYYY (report SQL uses DATE_FORMAT … '%d-%m-%Y')
    norm = text.replace(".", "-").replace("/", "-")
    parts = norm.split("-")
    if len(parts) != 3:
        return None
    try:
        d_d, d_m, d_y = int(parts[0]), int(parts[1]), int(parts[2])
    except ValueError:
        return None
    if d_y < 100:
        d_y += 2000 if d_y < 70 else 1900
    if d_m != month or d_y != year:
        return None
    if 1 <= d_d <= days_in_month:
        return d_d
    return None


def _parse_calendar_day_from_dispatch_row(
    row: Dict[str, Any], month: int, year: int, days_in_month: int
) -> Optional[int]:
    """Return calendar day-of-month (1..days_in_month) for CS_DATE–aligned dispatch row, or None."""
    raw = _first_matching_key(
        row,
        (
            REQUESTED_DATE_COL,
            "Requested Date",
            "requested date",
        ),
    )
    return _parse_calendar_day_value(raw, month, year, days_in_month)


def _aggregate_dispatch_rows(
    rows: List[Dict[str, Any]],
    month: int,
    year: int,
    days_in_month: int,
) -> Tuple[Dict[str, Dict[int, float]], Dict[int, float]]:
    """Sum dispatched qty by normalized part and by calendar day (CS_DATE via Requested Date column)."""
    part_day: Dict[str, Dict[int, float]] = {}
    day_totals: Dict[int, float] = {}
    for r in rows:
        day_i = _parse_calendar_day_from_dispatch_row(r, month, year, days_in_month)
        if day_i is None:
            continue
        dq = _to_float(
            _first_matching_key(
                r,
                (
                    DISPATCHED_QTY_COL,
                    "Dispatched Qty(Nos)",
                    "SD_LOTSIZE",
                ),
            )
        )
        # Always credit daily totals — part keys can differ by driver/casing; skipping rows
        # previously dropped all dispatch qty from Grand Total dayDispatch.
        day_totals[day_i] = day_totals.get(day_i, 0.0) + dq
        pk = _normalize_part_key(
            _first_matching_key(
                r,
                (
                    PART_NO_COL,
                    "CO_PARTNO",
                    "CO_partNo",
                    "co_partno",
                ),
            )
        )
        if not pk:
            continue
        part_day.setdefault(pk, {})
        part_day[pk][day_i] = part_day[pk].get(day_i, 0.0) + dq
    return part_day, day_totals


def _aggregate_dispatch_totals_by_part(rows: List[Dict[str, Any]]) -> Dict[str, float]:
    """Sum current-month dispatched qty by normalized part key."""
    out: Dict[str, float] = {}
    for r in rows:
        pk = _normalize_part_key(
            _first_matching_key(
                r,
                (
                    PART_NO_COL,
                    "CO_PARTNO",
                    "CO_partNo",
                    "co_partno",
                ),
            )
        )
        if not pk:
            continue
        dq = _to_float(
            _first_matching_key(
                r,
                (
                    DISPATCHED_QTY_COL,
                    "Dispatched Qty(Nos)",
                    "SD_LOTSIZE",
                ),
            )
        )
        out[pk] = out.get(pk, 0.0) + dq
    return out


def _fetch_dispatch_between_dates(month: int, year: int, days_in_month: int) -> List[Dict[str, Any]]:
    templates = _load_dispatch_calendar_query_templates()
    qt = templates.get(DISPATCH_BETWEEN_DATES_REPORT_ID, "")
    if not qt:
        logger.warning("Dispatch between dates query template not found in source JSON")
        return []
    from_date = f"01-{month:02d}-{year}"
    to_date = f"{days_in_month:02d}-{month:02d}-{year}"
    try:
        sql, params = reports_store.compile_report_query(
            qt,
            {"fromDate": from_date, "toDate": to_date},
        )
        return list(fetch_all(sql, tuple(params)))
    except Exception as e:
        logger.exception("Dispatch calendar: dispatch report query failed: %s", e)
        return []


def _is_incomplete_dispatch_row(row: Dict[str, Any], eps: float = 1e-9) -> bool:
    """True when the part has schedule and Dispatched % is not 100."""
    total_qty = _to_float(row.get(TOTAL_QTY_COL))
    if total_qty <= eps:
        return False
    pct_raw = row.get(DISPATCHED_PCT_COL)
    if pct_raw is None:
        return True
    try:
        return abs(float(pct_raw) - 100.0) > eps
    except (TypeError, ValueError):
        return True


def _filter_dispatch_balance_rows(payload: Dict[str, Any]) -> None:
    """Keep only parts where Dispatched % != 100 (balance dispatch remaining)."""
    rows = payload.get("rows") or []
    row_meta = list(payload.get("rowMeta") or [])

    kept_rows: List[Dict[str, Any]] = []
    kept_meta: List[Any] = []
    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        meta = row_meta[idx] if idx < len(row_meta) else {}
        if isinstance(meta, dict) and meta.get("isGrandTotal"):
            continue
        if _is_incomplete_dispatch_row(row):
            kept_rows.append(row)
            kept_meta.append(meta)

    payload["rows"] = kept_rows
    payload["rowMeta"] = kept_meta


def build_dispatch_calendar_payload(
    month: int,
    year: int,
    row_filter: Optional[str] = None,
) -> Dict[str, Any]:
    if month < 1 or month > 12:
        raise ValueError("month must be 1–12")
    if year < 1900 or year > 2100:
        raise ValueError("year out of range")

    templates = _load_dispatch_calendar_query_templates()
    mo_qt = templates.get(MONTHLY_ORDER_REPORT_ID, "")
    if not mo_qt:
        raise ValueError("Monthly Order query template not found in source JSON")
    st_qt = templates.get(STOCK_REPORT_ID, "")
    if not st_qt:
        raise ValueError("Current Consolidated Component Stock query template not found in source JSON")

    mo_sql, mo_params = reports_store.compile_report_query(
        mo_qt,
        {"month": month, "year": year},
    )
    st_sql, st_params = reports_store.compile_report_query(
        st_qt,
        {},
    )

    mo_rows = fetch_all(mo_sql, tuple(mo_params))
    st_rows = fetch_all(st_sql, tuple(st_params))

    stock_index = _build_stock_index(st_rows)

    days_in_month = calendar.monthrange(year, month)[1]

    columns: List[str] = list(mo_rows[0].keys()) if mo_rows else []
    if columns and PART_NO_COL in columns and TOTAL_QTY_COL in columns:
        day_cols = [c for c in columns if str(c).lower().startswith("day ")]
        columns = [
            PART_NO_COL,
            NO_OF_OPERATIONS_COL,
            TOTAL_QTY_COL,
            TOTAL_DISPATCHED_QTY_COL,
            DISPATCHED_PCT_COL,
        ] + day_cols

    grand_total_stock_fg = 0.0
    grand_total_stock_wip = 0.0
    grand_scheduled_by_day: Dict[int, float] = {}

    for raw in mo_rows:
        if _is_grand_total_row(raw):
            for d in range(1, days_in_month + 1):
                grand_scheduled_by_day[d] = _to_float(raw.get(_day_column_key(d)))
            continue
        pk = _normalize_part_key(_mo_part_no_raw(raw))
        if not pk:
            continue
        fg, wip = stock_index.get(pk, (0.0, 0.0))
        grand_total_stock_fg += fg
        grand_total_stock_wip += wip

    dispatch_rows = _fetch_dispatch_between_dates(month, year, days_in_month)
    part_dispatched_totals = _aggregate_dispatch_totals_by_part(dispatch_rows)

    eps_pct = 1e-9
    day_scheduled_json: Dict[str, float] = {}
    day_dispatched_json: Dict[str, float] = {}
    day_pct_json: Dict[str, Optional[float]] = {}
    allocated_day_dispatched_totals: Dict[int, float] = {d: 0.0 for d in range(1, days_in_month + 1)}
    grand_total_dispatched_qty = 0.0

    part_day_dispatch: Dict[str, Dict[str, Dict[str, float]]] = {}
    row_dispatched_totals_by_pk: Dict[str, float] = {}
    for raw in mo_rows:
        if _is_grand_total_row(raw):
            continue
        pk = _normalize_part_key(_mo_part_no_raw(raw))
        if not pk:
            continue
        dispatched_left = float(part_dispatched_totals.get(pk, 0.0))
        total_dispatched_for_row = dispatched_left
        by_day: Dict[str, Dict[str, float]] = {}
        for d in range(1, days_in_month + 1):
            scheduled = _to_float(raw.get(_day_column_key(d)))
            dispatched = 0.0
            # Allocate month dispatched qty sequentially to days that have schedule.
            if scheduled > eps_pct and dispatched_left > eps_pct:
                dispatched = min(scheduled, dispatched_left)
                dispatched_left -= dispatched
                allocated_day_dispatched_totals[d] = allocated_day_dispatched_totals.get(d, 0.0) + dispatched
            by_day[str(d)] = {
                "dispatched": round(dispatched, 4),
                "scheduledQty": round(scheduled, 4),
            }
        part_day_dispatch[pk] = by_day
        row_dispatched_totals_by_pk[pk] = round(total_dispatched_for_row, 4)
        grand_total_dispatched_qty += total_dispatched_for_row

    for d in range(1, days_in_month + 1):
        sch = float(grand_scheduled_by_day.get(d, 0.0))
        dis = float(allocated_day_dispatched_totals.get(d, 0.0))
        day_scheduled_json[str(d)] = round(sch, 4)
        day_dispatched_json[str(d)] = round(dis, 4)
        if sch > eps_pct:
            day_pct_json[str(d)] = round(100.0 * dis / sch, 2)
        else:
            day_pct_json[str(d)] = None

    row_meta: List[Optional[Dict[str, Any]]] = []
    for raw in mo_rows:
        pk = _normalize_part_key(_mo_part_no_raw(raw))
        total_qty = _to_float(raw.get(TOTAL_QTY_COL))
        dispatched_total = row_dispatched_totals_by_pk.get(pk, 0.0) if pk else 0.0
        raw[TOTAL_DISPATCHED_QTY_COL] = round(dispatched_total, 4)
        raw[DISPATCHED_PCT_COL] = round((100.0 * dispatched_total / total_qty), 2) if total_qty > eps_pct else None
        if _is_grand_total_row(raw):
            gt_total = _to_float(raw.get(TOTAL_QTY_COL))
            raw[TOTAL_DISPATCHED_QTY_COL] = round(grand_total_dispatched_qty, 4)
            raw[DISPATCHED_PCT_COL] = (
                round((100.0 * grand_total_dispatched_qty / gt_total), 2)
                if gt_total > eps_pct
                else None
            )
            row_meta.append(
                {
                    "isGrandTotal": True,
                    "grandTotalStock": {
                        "stockFg": round(grand_total_stock_fg, 4),
                        "stockWip": round(grand_total_stock_wip, 4),
                    },
                }
            )
            continue

        fg, wip = stock_index.get(pk, (0.0, 0.0))
        day_status: Dict[str, Dict[str, str]] = {}
        fg_left = float(fg)
        wip_left = float(wip)

        for d in range(1, 32):
            if d > days_in_month:
                break
            qty = _to_float(raw.get(_day_column_key(d)))
            if qty <= eps_pct:
                continue
            dispatched = float(part_day_dispatch.get(pk, {}).get(str(d), {}).get("dispatched", 0.0))
            dispatch_complete = qty > eps_pct and dispatched + eps_pct >= qty
            if dispatch_complete:
                day_status[str(d)] = {"status": "dispatched"}
                continue
            # Sequential availability rule:
            # Evaluate each day against remaining FG/WIP after earlier open schedules.
            # Only outstanding demand (scheduled - already dispatched for that day) consumes stock.
            need = max(0.0, qty - dispatched)
            if need <= eps_pct:
                day_status[str(d)] = {"status": "dispatched"}
                continue
            if fg_left + eps_pct >= need:
                status = "full"
            elif fg_left > eps_pct or wip_left > eps_pct:
                status = "partial"
            else:
                status = "short"
            # Consume from FG first, then WIP, to carry forward realistic remaining availability.
            use_fg = min(fg_left, need)
            fg_left -= use_fg
            need -= use_fg
            if need > eps_pct:
                use_wip = min(wip_left, need)
                wip_left -= use_wip
            day_status[str(d)] = {"status": status}

        row_meta.append(
            {
                "stockFg": round(fg, 4),
                "stockWip": round(wip, 4),
                "dayStatus": day_status,
            }
        )

    result = {
        "month": month,
        "year": year,
        "daysInMonth": days_in_month,
        "columns": columns,
        "rows": [
            _serialize_row({c: r.get(c) for c in columns}) if columns else _serialize_row(r)
            for r in mo_rows
        ],
        "rowMeta": row_meta,
        "grandTotalStock": {
            "stockFg": round(grand_total_stock_fg, 4),
            "stockWip": round(grand_total_stock_wip, 4),
        },
        "dayDispatch": {
            "scheduled": day_scheduled_json,
            "dispatched": day_dispatched_json,
            "pct": day_pct_json,
        },
        "partDayDispatch": part_day_dispatch,
    }

    row_filter_key = (row_filter or "").strip().lower()
    if row_filter_key == "balance":
        _filter_dispatch_balance_rows(result)
        result["rowFilter"] = "balance"

    return result


def get_dispatch_schedule_by_part(month: int, year: int) -> Dict[str, Dict[str, Any]]:
    """Dispatch schedule entries keyed by normalized part_no."""
    templates = _load_dispatch_calendar_query_templates()
    mo_qt = templates.get(MONTHLY_ORDER_REPORT_ID, "")
    if not mo_qt:
        return {}
    mo_sql, mo_params = reports_store.compile_report_query(
        mo_qt,
        {"month": month, "year": year},
    )
    mo_rows = fetch_all(mo_sql, tuple(mo_params))
    out: Dict[str, Dict[str, Any]] = {}
    for raw in mo_rows:
        if _is_grand_total_row(raw):
            continue
        pk = _normalize_part_key(_mo_part_no_raw(raw))
        if not pk:
            continue
        out[pk] = {
            "partNo": str(_mo_part_no_raw(raw) or "").strip(),
            "scheduledQty": _to_float(raw.get(TOTAL_QTY_COL)),
        }
    return out


def get_dispatch_day_qty_by_part(month: int, year: int) -> Dict[str, Dict[str, Any]]:
    """Per-part dispatch scheduled qty by calendar day (day_1 … day_31)."""
    templates = _load_dispatch_calendar_query_templates()
    mo_qt = templates.get(MONTHLY_ORDER_REPORT_ID, "")
    if not mo_qt:
        return {}
    mo_sql, mo_params = reports_store.compile_report_query(
        mo_qt,
        {"month": month, "year": year},
    )
    mo_rows = fetch_all(mo_sql, tuple(mo_params))
    days_in_month = calendar.monthrange(year, month)[1]
    out: Dict[str, Dict[str, Any]] = {}
    for raw in mo_rows:
        if _is_grand_total_row(raw):
            continue
        pk = _normalize_part_key(_mo_part_no_raw(raw))
        if not pk:
            continue
        day_qty: Dict[str, float] = {}
        for d in range(1, days_in_month + 1):
            day_qty[f"day_{d}"] = _to_float(raw.get(_day_column_key(d)))
        out[pk] = {
            "partNo": str(_mo_part_no_raw(raw) or "").strip(),
            "days": day_qty,
        }
    return out


def get_scheduled_qty_by_part(month: int, year: int) -> Dict[str, float]:
    """Per-part Total Scheduled Qty from the dispatch monthly-order report."""
    return {
        pk: float(info.get("scheduledQty") or 0.0)
        for pk, info in get_dispatch_schedule_by_part(month, year).items()
    }


def get_dispatch_kpi(month: int, year: int) -> Dict[str, Any]:
    """Grand-total dispatch KPI aligned with the Dispatch Calendar toolbar."""
    payload = build_dispatch_calendar_payload(month, year)
    rows = payload.get("rows") or []
    row_meta = payload.get("rowMeta") or []
    scheduled = 0.0
    dispatched = 0.0
    eps = 1e-9
    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        meta = row_meta[idx] if idx < len(row_meta) and isinstance(row_meta[idx], dict) else {}
        if not meta.get("isGrandTotal"):
            continue
        scheduled = _to_float(row.get(TOTAL_QTY_COL))
        dispatched = _to_float(row.get(TOTAL_DISPATCHED_QTY_COL))
        break
    pct: Optional[float] = (
        round((100.0 * dispatched / scheduled), 2) if scheduled > eps else None
    )
    return {
        "scheduled": round(scheduled, 4),
        "dispatched": round(dispatched, 4),
        "pct": pct,
    }
