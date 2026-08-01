package com.ruoyi.system.mapper.operation.customs;

import com.ruoyi.system.domain.operation.customs.CustomsPackingSavedPayload;
import com.ruoyi.system.domain.operation.customs.CustomsPackingSubmission;
import java.util.List;
import org.apache.ibatis.annotations.Param;

public interface CustomsPackingSubmissionMapper
{
    List<CustomsPackingSubmission> selectCandidateList(
            @Param("inboundPlanId") String inboundPlanId,
            @Param("status") String status);

    List<CustomsPackingSavedPayload> selectLatestSavedPayloads(
            @Param("inboundPlanId") String inboundPlanId);

    Integer selectPositionTypeByInboundPlanId(
            @Param("inboundPlanId") String inboundPlanId);

    int countExpectedShipments(
            @Param("inboundPlanId") String inboundPlanId);

    CustomsPackingSubmission selectById(@Param("id") Long id);

    CustomsPackingSubmission selectByInboundPlanId(
            @Param("inboundPlanId") String inboundPlanId);

    List<CustomsPackingSubmission> selectPending(@Param("limit") int limit);

    int insertReady(CustomsPackingSubmission submission);

    int claimForSubmit(
            @Param("inboundPlanId") String inboundPlanId,
            @Param("operator") String operator);

    int updatePrepared(
            @Param("id") Long id,
            @Param("sid") Long sid,
            @Param("positionType") Integer positionType,
            @Param("payloadHash") String payloadHash,
            @Param("requestBody") String requestBody);

    int updateAfterSubmit(
            @Param("id") Long id,
            @Param("status") String status,
            @Param("taskId") String taskId,
            @Param("requestId") String requestId,
            @Param("responseBody") String responseBody,
            @Param("errorMessage") String errorMessage);

    int updateAfterPoll(
            @Param("id") Long id,
            @Param("status") String status,
            @Param("requestId") String requestId,
            @Param("responseBody") String responseBody,
            @Param("errorMessage") String errorMessage);
}
