package com.mhk.erp.component.service;

import com.mhk.erp.component.repository.ComponentLotStockRepository;
import com.mhk.erp.component.repository.ComponentRepository;
import com.mhk.erp.component.repository.ComponentStockRepository;
import com.mhk.erp.component.repository.ComponentTransactionRepository;
import com.mhk.erp.customer.repository.CustomerRepository;
import com.mhk.erp.domain.*;
import com.mhk.erp.dto.ComponentInventory;
import com.mhk.erp.dto.StockTransferLotWrapperData;
import com.mhk.erp.dto.StockTransferWrapperData;
import com.mhk.erp.util.DateUtil;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.stream.Collectors;

@Slf4j
@Service("componentService")
@Transactional(propagation = Propagation.REQUIRED, readOnly = true)
public class ComponentServiceImpl  implements ComponentService {

    @Autowired
    private ComponentRepository componentRepository;

    @Autowired
    private ComponentLotStockRepository componentLotStockRepository;

    @Autowired
    private ComponentStockRepository componentStockRepository;

    @Autowired
    private ComponentTransactionRepository componentTransactionRepository;



    @Autowired
    private CustomerRepository customerRepository;

    @Override
    public List<Component> getAllComponentByCustId(Integer custId) {
        return componentRepository.findAllByCustomerIdAndStatusId(custId,"Y",Sort.by(Sort.Order.asc("partName")));
    }

    @Override
    public Component details(Integer compId) {
        Component component = componentRepository.findById(compId).get();
        Customer customer = customerRepository.findById(component.getCustomerId()).get();
        component.setCustomerName(customer.getCustomerName());
        return component;
    }

    @Override
    public List<ComponentInventory> getComponentInventoryList(Integer compId, Integer stageId, Integer plantId) {
        List<Object[]> results =  componentRepository.getComponentInventoryList(compId, stageId, plantId);

        return results.stream()
                .map(row -> new ComponentInventory(
                        (String) row[0],      // Cast the first element to String (lotNo)
                        (Double) row[1]))     // Cast the second element to Double (qtyNo)
                .collect(Collectors.toList());
    }

    @Override
    @Transactional(readOnly = false)
    public void reduceStock(StockTransferWrapperData stData) {
        List<StockTransferLotWrapperData> lotList = stData.getLineItems();
        lotList.stream().forEach(lotData -> {
            saveComponentTransaction(stData,lotData);
            saveComponentLotStock(stData,lotData);
        });
        saveComponentStock(stData);
    }

    @Override
    public int getRMIdByComponentId(int compId) {
        return componentRepository.getRMIdByComponentId(compId);
    }

    @Transactional(readOnly = false)
    public void saveComponentStock(StockTransferWrapperData stData) {
        ComponentStock cl = componentStockRepository.findMatchComponentStock(stData.getCompId(),
                stData.getPlantId(),stData.getCsStageId()).get(0);
        int qty = cl.getCsQty() - stData.getTotalQty().intValue();
        if(qty >0) {
            cl.setCsQty(qty);

        }
        else {
            cl.setCsQty(0);

        }
        componentStockRepository.save(cl);

    }

    @Transactional(readOnly = false)
    public void saveComponentLotStock(StockTransferWrapperData stData,StockTransferLotWrapperData lotData) {
        ComponentLotStock cl = componentLotStockRepository.findByClLotNo(lotData.getLotNo());
        cl.setClDespatch(cl.getClDespatch() + lotData.getQty().intValue());
        cl.setClTotal((cl.getClProduction() + cl.getClAdjustment()) - (cl.getClScrap() + cl.getClDespatch()) );
        if(cl.getClTotal() <0) {
            cl.setClTotal(0);
        }
        componentLotStockRepository.save(cl);
    }

    @Transactional(readOnly = false)
    public void saveComponentTransaction(StockTransferWrapperData stData,StockTransferLotWrapperData lotData) {
        ComponentTransaction ct = new ComponentTransaction();
        ct.setCtCompId(stData.getCompId());
        ct.setCtPlantId(stData.getPlantId());
        ct.setCtMovement("O");
        ct.setCtQty(lotData.getQty().intValue());
        ct.setCtOPStage(stData.getCsStageId());
        ct.setCtDate(DateUtil.getCurrentCalendarDate());
        ct.setCtLotNo(lotData.getLotNo());
        ct.setCtNextStage(stData.getCsStageId());

        if(stData.getCsStageId() == 6) {
            ct.setCtFG("Y");
        }else {
            ct.setCtFG("N");
        }
        ct.setCtLastUpdatedBy(stData.getCreatedByUserId());
        ct.setCtLastUpdated(DateUtil.getCurrentCalendarDate());
        ct.setCtSource(18);
        componentTransactionRepository.save(ct);
    }
}



