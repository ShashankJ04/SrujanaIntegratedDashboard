import type { Generated } from "kysely";

// ── scheduled_production ───────────────────────────────────────────
export interface ScheduledProductionTable {
  PS_ID: Generated<number>;
  PS_SMID: number;
  PS_PLANTID: number | null;
  PS_PARENTCOMPID: number;
  PS_MCID: number;
  PS_TOOLID: number;
  PS_QTY: number;
  PS_QTYKG: number;
  PS_DATE: string; // DATE
  PS_STATUS: number;
  PS_LASTUPDATEDBY: number;
  PS_LASTUPDATED: Generated<string>;
}

// ── components_tool ────────────────────────────────────────────────
export interface ComponentsToolTable {
  CT_ID: Generated<number>;
  CT_COMPID: number;
  CT_SUPPLIERID: number;
  CT_DRAWINGNO: string;
  CT_TOOLNO: string;
  CT_DATE: string; // DATE
  CT_RMID: number;
  CT_PITCH: number;
  CT_NO_OF_CAVITY: number;
  CT_PPC: string;
  CT_NO_OF_OPERATION: number;
  CT_CPID: number;
  CT_PPCTOOLID: number;
  CT_ORDER: number;
  CT_ATTACHMENT: string | null;
  CT_ACTIVEYN: string;
  CT_LASTUPDATEDBY: number;
  CT_LASTUPADTED: Generated<string>;
}

// ── components ─────────────────────────────────────────────────────
export interface ComponentsTable {
  CO_ID: Generated<number>;
  CO_CUSTID: number;
  CO_PARENTID: number;
  CO_EQID: number;
  CO_PARTNO: string;
  CO_PARTNAME: string;
  CO_CLASS: string | null;
  CO_WEIGHT: number;
  CO_MATERIALTYPEID: number;
  CO_GRADEID: number;
  CO_WIDTH: number;
  CO_LENGTH: number;
  CO_REVISION: string | null;
  CO_DATE: string;
  CO_ELECTROPLATING: number;
  CO_MICRON: number;
  CO_FINISH: number;
  CO_REMARKS: string | null;
  CO_ATTACHMENT: string | null;
  CO_ACTIVEYN: string;
  CO_LASTUPDATEDBY: number;
  CO_LASTUPDATED: Generated<string>;
}

// ── machinemaster ──────────────────────────────────────────────────
export interface MachineMasterTable {
  MCM_Id: Generated<number>;
  MCM_PLANTID: number;
  MCM_Name: string | null;
  MCM_Type: number;
  MCM_PPC: string | null;
  MCM_Make: string;
  MCM_Capacity: string;
  MCM_ACTIVEYN: string;
  MCM_LASTUPDATED: Generated<string>;
}

// ── production_details ─────────────────────────────────────────────
export interface ProductionDetailsTable {
  PD_ID: Generated<number>;
  PD_PARENTPDID: number;
  PD_PLANTID: number;
  PD_PSID: number;
  PD_LotNo: string;
  PD_DATE: string; // DATETIME
  PD_MCID: number;
  PD_TOOLID: number;
  PD_OPERATION: number;
  PD_RMID: number;
  PD_HEATNO: string | null;
  PD_BATCHNO: string | null;
  PD_PRODQTY: number;
  PD_QTYKG: number;
  PD_SFREJECT: number | null;
  PD_NETQTY: number;
  PD_SWQTY: number | null;
  PD_SCRAPQTY: number;
  PD_QASTATUS: string | null;
  PD_CMId: number;
  PD_CREATEDBY: number;
  PD_CREATEDDT: string;
  PD_LASTUPDATEDBY: number;
  PD_LASTUPDATED: Generated<string>;
  PD_OPID: number | null;
}

// ── supplier ───────────────────────────────────────────────────────
export interface SupplierTable {
  ss_Id: Generated<number>;
  ss_Name: string | null;
  ss_SupplierType: number | null;
  ss_State: number;
}

// ── customer ───────────────────────────────────────────────────────
export interface CustomerTable {
  CU_Id: Generated<number>;
  CU_Name: string | null;
}

// ── tool_life ──────────────────────────────────────────────────────
export interface ToolLifeTable {
  TL_tool_id: number;
  TL_tool_number: string;
  TL_life_span: number;
  TL_spm: number;
  TL_preventive_maintenance_strokes: number;
  TL_created_at: Generated<string>;
}

// ── preventive_maintenance ─────────────────────────────────────────
export interface PreventiveMaintenanceTable {
  PM_id: Generated<number>;
  PM_tool_id: number;
  PM_tool_number: string;
  PM_date: string;
  PM_current_stroke: number;
  PM_next_stroke: number;
  PM_maintenance_attachment: string | null;
}

// ── users ───────────────────────────────────────────────────────
export interface UsersTable {
  US_ID: Generated<number>;
  US_Login: string;
  US_Password: string | null;
  US_FirstName: string | null;
  US_LastName: string | null;
  US_CurrentYn: string | null;
}

// ── Database aggregate ─────────────────────────────────────────────
export interface Database {
  scheduled_production: ScheduledProductionTable;
  components_tool: ComponentsToolTable;
  components: ComponentsTable;
  machinemaster: MachineMasterTable;
  production_details: ProductionDetailsTable;
  supplier: SupplierTable;
  customer: CustomerTable;
  tool_life: ToolLifeTable;
  preventive_maintenance: PreventiveMaintenanceTable;
  users: UsersTable;
}
