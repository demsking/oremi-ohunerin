# Copyright 2026 Sébastien Demanou. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
import json
import os
import re


def main() -> None:
  base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

  # Paths
  pyproject_path = os.path.join(base_dir, 'pyproject.toml')
  openapi_path = os.path.join(base_dir, 'ohunerin/doc/openapi.json')
  documentation_path = os.path.join(base_dir, 'ohunerin/DOCUMENTATION.md')
  public_dir = os.path.join(base_dir, 'public')
  output_path = os.path.join(public_dir, 'openapi.json')

  # 1. Read version from pyproject.toml
  with open(pyproject_path, encoding='utf-8') as f:
    content = f.read()
    match = re.search(r'version\s*=\s*"([^"]+)"', content)
    if not match:
      raise ValueError('Could not find version in pyproject.toml')
    version = match.group(1)

  # 2. Read description from DOCUMENTATION.md
  with open(documentation_path, encoding='utf-8') as f:
    description = f.read()

  # 3. Read openapi.json template
  with open(openapi_path, encoding='utf-8') as f:
    spec = json.load(f)

  # 4. Update spec
  spec['info']['description'] = description
  spec['info']['version'] = version

  # 5. Ensure public directory exists
  os.makedirs(public_dir, exist_ok=True)

  # 6. Save updated spec
  with open(output_path, 'w', encoding='utf-8') as f:
    json.dump(spec, f, indent=2, ensure_ascii=False)

  print(f'Successfully generated openapi.json at {output_path} (version: {version})')


if __name__ == '__main__':
  main()
