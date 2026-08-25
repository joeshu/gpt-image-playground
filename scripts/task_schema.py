"""Canonical, dependency-free task normalization shared by API and agents."""


SCHEMA_VERSION = 1
FORBIDDEN_FIELDS = {'endpoint', 'agent_endpoint', 'api_key', 'api_key_env'}
ENUMS = {
    'execution_mode': {'auto', 'native', 'script'},
    'api_mode': {'images', 'responses'},
    'quality': {'low', 'medium', 'high', 'auto'},
    'output_format': {'png', 'jpeg', 'jpg', 'webp'},
    'background': {'auto', 'opaque', 'transparent'},
}


class TaskValidationError(ValueError):
    def __init__(self, message, *, code='request_invalid', field=None):
        super().__init__(message)
        self.code = code
        self.field = field


def _integer(result, field, minimum, maximum):
    if field not in result or result[field] is None:
        return
    try:
        value = int(result[field])
    except (TypeError, ValueError) as exc:
        raise TaskValidationError(f'{field} 必须是整数', field=field) from exc
    if not minimum <= value <= maximum:
        raise TaskValidationError(f'{field} 必须在 {minimum}-{maximum} 之间', field=field)
    result[field] = value


def normalize_task(task, *, batch=False, validate_image=None, strip_sensitive=True):
    if not isinstance(task, dict):
        raise TaskValidationError('请求体必须是 JSON 对象')
    result = {key: value for key, value in task.items() if not strip_sensitive or key not in FORBIDDEN_FIELDS}
    result['schema_version'] = SCHEMA_VERSION

    if 'prompt' in result:
        if not isinstance(result['prompt'], str) or not result['prompt'].strip():
            raise TaskValidationError('prompt 必须是非空字符串', field='prompt')
        result['prompt'] = result['prompt'].strip()

    for field, allowed in ENUMS.items():
        if field in result and result[field] is not None and result[field] not in allowed:
            raise TaskValidationError(f'{field} 不支持: {result[field]}', field=field)
    _integer(result, 'n', 1, 16)
    _integer(result, 'concurrency', 1, 16)
    _integer(result, 'timeout', 1, 1200)

    for key in ('images', 'image_urls'):
        if key not in result:
            continue
        values = result[key]
        if not isinstance(values, list) or len(values) > 16:
            raise TaskValidationError('参考图必须是最多 16 项的数组', field=key)
        result[key] = [validate_image(item) if validate_image else item for item in values]
    if result.get('mask') and validate_image:
        result['mask'] = validate_image(result['mask'])

    if 'tasks' in result:
        values = result['tasks']
        if not isinstance(values, list) or not values or len(values) > 100:
            raise TaskValidationError('tasks 必须是 1-100 项的数组', field='tasks')
        result['tasks'] = [normalize_task(item, validate_image=validate_image, strip_sensitive=strip_sensitive) for item in values]
    if not batch and 'tasks' in result:
        raise TaskValidationError('单任务接口不接受 tasks，请使用 /v1/batch', field='tasks')
    if 'tasks' not in result and 'prompt' not in result:
        raise TaskValidationError('缺少 prompt', field='prompt')
    return result
