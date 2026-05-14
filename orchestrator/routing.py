from orchestrator.schemas import SynthesisVerdict


def should_request_otp(verdict: SynthesisVerdict) -> bool:
    return verdict.verdict == "OTP_INTERLOCK"
