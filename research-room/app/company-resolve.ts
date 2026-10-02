// 用户可以输简称：开查之前请后端把名字定成全称（/api/companies/resolve）。
// 精确对上就直接查；简称常有几家同名（"巨鲸财富"会同时命中巨鲸财富管理和巨鲸资产管理），列出来让用户选，不替他挑。

export type CompanyCandidate = {
  name: string;
  code: string | null;
  founded: string | null;
  status: string | null;
};

export type CompanyResolution = {
  query: string;
  exact: boolean;
  name: string | null;
  candidates: CompanyCandidate[];
  source: string;
  note: string | null;
};

const optionalText = (value: unknown) => value == null || typeof value === 'string';

/** 失败或取消返回 null；调用方应让用户重试或明确确认全称，不能自动按简称开查。 */
export async function resolveCompany(
  query: string,
  fetchImpl: typeof fetch = fetch,
  { signal, timeoutMs = 8000 }: { signal?: AbortSignal; timeoutMs?: number } = {},
): Promise<CompanyResolution | null> {
  if (signal?.aborted) return null;
  const controller = new AbortController();
  let cancel!: () => void;
  // Also settle if a transport or response body does not honor AbortSignal.
  const cancelled = new Promise<null>(resolve => {
    cancel = () => { controller.abort(); resolve(null); };
  });
  const timer = setTimeout(cancel, timeoutMs);
  signal?.addEventListener('abort', cancel, { once: true });
  try {
    const lookup = (async () => {
      const response = await fetchImpl(`/api/companies/resolve?q=${encodeURIComponent(query.trim())}`, {
        signal: controller.signal,
      });
      if (!response.ok) return null;
      const data = (await response.json()) as CompanyResolution;
      if (typeof data?.exact !== 'boolean' || !Array.isArray(data.candidates) ||
          (data.exact && (typeof data.name !== 'string' || !data.name.trim())) ||
          !optionalText(data.note) || !data.candidates.every(candidate =>
            candidate !== null && typeof candidate === 'object' && !Array.isArray(candidate) &&
            typeof candidate.name === 'string' && candidate.name.trim().length > 0 &&
            [candidate.code, candidate.founded, candidate.status].every(optionalText))) return null;
      return data;
    })();
    return await Promise.race([lookup, cancelled]);
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener('abort', cancel);
  }
}

export function candidateLine(c: CompanyCandidate): string {
  return [c.status, c.founded && `成立于 ${c.founded}`, c.code].filter(Boolean).join(' · ');
}
