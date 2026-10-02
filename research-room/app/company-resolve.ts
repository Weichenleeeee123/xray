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

/** 连不上返回 null：找名字这一步不挡路，调用方按原样查。 */
export async function resolveCompany(
  query: string,
  fetchImpl: typeof fetch = fetch,
): Promise<CompanyResolution | null> {
  try {
    const response = await fetchImpl(`/api/companies/resolve?q=${encodeURIComponent(query.trim())}`);
    if (!response.ok) return null;
    const data = (await response.json()) as CompanyResolution;
    if (typeof data?.exact !== 'boolean' || !Array.isArray(data.candidates)) return null;
    return data;
  } catch {
    return null;
  }
}

export function candidateLine(c: CompanyCandidate): string {
  return [c.status, c.founded && `成立于 ${c.founded}`, c.code].filter(Boolean).join(' · ');
}
