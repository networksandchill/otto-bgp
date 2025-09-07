"""IRR Proxy API endpoints for Otto BGP WebUI"""
import subprocess
from fastapi import APIRouter, Depends, HTTPException
from webui.core.security import require_role
from webui.core.audit import audit_log

router = APIRouter()


def head_tail(s: str, n: int = 400) -> str:
    """Return head and tail of string, with truncation indicator if needed"""
    if not s:
        return ''
    if len(s) <= 2 * n:
        return s
    return s[:n] + '\n...\n' + s[-n:]


@router.post('/test')
async def test_proxy(user: dict = Depends(require_role('admin'))):
    """Test IRR proxy connectivity by running otto-bgp test-proxy command"""
    try:
        # Run the otto-bgp test-proxy command
        result = subprocess.run(
            ['./otto-bgp', 'test-proxy', '--test-bgpq4', '-v'],
            capture_output=True,
            text=True,
            timeout=60
        )

        # Capture stdout and stderr
        stdout = result.stdout
        stderr = result.stderr

        # Get head and tail for preview (avoid huge outputs)
        preview_out = head_tail(stdout)
        preview_err = head_tail(stderr)

        if result.returncode == 0:
            audit_log('irr_proxy_test_success', user=user.get('sub'))
            return {
                "success": True,
                "message": "IRR proxy test completed successfully",
                "stdout": preview_out,
                "stderr": preview_err
            }
        else:
            audit_log('irr_proxy_test_failed', user=user.get('sub'))
            return {
                "success": False,
                "message": f"Test failed with exit code {result.returncode}",
                "stdout": preview_out,
                "stderr": preview_err
            }

    except subprocess.TimeoutExpired:
        audit_log('irr_proxy_test_timeout', user=user.get('sub'))
        raise HTTPException(
            status_code=504,
            detail="IRR proxy test timed out after 60 seconds"
        )
    except FileNotFoundError:
        audit_log('irr_proxy_test_binary_not_found', user=user.get('sub'))
        raise HTTPException(
            status_code=500,
            detail=("otto-bgp binary not found. "
                    "Ensure Otto BGP is properly installed.")
        )
    except Exception as e:
        audit_log('irr_proxy_test_error', user=user.get('sub'), error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected error during IRR proxy test: {str(e)}"
        )
