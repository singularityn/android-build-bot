#!/bin/bash

# ============================================================
# Singularity - Android ROM Signing Key Generator
# Generates private keys for signing custom ROM builds
# ============================================================

# Note: do NOT use 'set -e' here because make_key's EXIT trap returns exit code 1
# We verify key generation manually instead

# --- Colors ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${CYAN}============================================================${NC}"
echo -e "${CYAN}  Singularity - Android ROM Signing Key Generator${NC}"
echo -e "${CYAN}============================================================${NC}"
echo ""

# --- Prerequisite Check ---
if ! command -v openssl &> /dev/null; then
    echo -e "${RED}[ERROR] openssl not found! Install it first.${NC}"
    exit 1
fi

if [ ! -x "./development/tools/make_key" ]; then
    echo -e "${RED}[ERROR] ./development/tools/make_key not found!${NC}"
    echo -e "${RED}Make sure you run this script from your ROM source root directory.${NC}"
    exit 1
fi

if [ -d "vendor/lineage-priv/keys" ]; then
    echo -e "${YELLOW}[WARNING] vendor/lineage-priv/keys/ already exists!${NC}"
    read -p "Overwrite existing keys? This is IRREVERSIBLE (y/n): " overwrite
    if [[ $overwrite != "y" && $overwrite != "Y" ]]; then
        echo "Exiting without changes."
        exit 1
    fi
    rm -rf vendor/lineage-priv/keys
    rm -rf ~/.android-certs
fi

echo -e "${GREEN}[OK] Prerequisites verified${NC}"
echo ""

# --- Prompt the user for each part of the subject line ---
echo -e "${YELLOW}Fill in certificate details (press ENTER to use default in quotes):${NC}"
echo ""

read -p "Enter country code [ID]: " country
country=${country:-ID}

read -p "Enter state or province name [West Sumatera]: " state
state=${state:-West Sumatera}

read -p "Enter locality [Padang]: " locality
locality=${locality:-Padang}

read -p "Enter organization name [singularityn]: " organization
organization=${organization:-singularityn}

read -p "Enter organizational unit [singularityn]: " organizational_unit
organizational_unit=${organizational_unit:-singularityn}

read -p "Enter common name [singularityn]: " common_name
common_name=${common_name:-singularityn}

read -p "Enter email address [fariqhfebrian5@gmail.com]: " email
email=${email:-fariqhfebrian5@gmail.com}

# Construct the subject line
subject="/C=${country}/ST=${state}/L=${locality}/O=${organization}/OU=${organizational_unit}/CN=${common_name}/emailAddress=${email}"

# Print the subject line
echo ""
echo -e "${CYAN}Using Subject Line:${NC}"
echo -e "${GREEN}${subject}${NC}"
echo ""

# Prompt the user to verify if the subject line is correct
read -p "Is the subject line correct? (y/n): " confirmation

# Check the user's response
if [[ $confirmation != "y" && $confirmation != "Y" ]]; then
    echo "Exiting without changes."
    exit 1
fi

echo ""

# --- Create Keys (auto-skip password) ---
echo -e "${CYAN}Generating signing keys (no password for inline signing)...${NC}"
mkdir -p ~/.android-certs

KEYS="bluetooth media networkstack nfc platform releasekey sdk_sandbox shared testkey verifiedboot"
TOTAL=$(echo $KEYS | wc -w)
COUNT=0

for x in $KEYS; do
    COUNT=$((COUNT + 1))
    echo -e "${YELLOW}[${COUNT}/${TOTAL}] Generating key: ${x}${NC}"
    # Pipe empty line to auto-skip password prompt in make_key
    echo "" | ./development/tools/make_key ~/.android-certs/$x "$subject"
done

echo ""
echo -e "${GREEN}[OK] All ${TOTAL} key pairs generated!${NC}"

# --- Verify keys were created ---
echo -e "${CYAN}Verifying generated keys...${NC}"
MISSING=0
for x in $KEYS; do
    if [ ! -f ~/.android-certs/$x.pk8 ] || [ ! -f ~/.android-certs/$x.x509.pem ]; then
        echo -e "${RED}[MISSING] $x.pk8 or $x.x509.pem${NC}"
        MISSING=$((MISSING + 1))
    fi
done

if [ $MISSING -gt 0 ]; then
    echo -e "${RED}[ERROR] $MISSING key(s) failed to generate! Check errors above.${NC}"
    exit 1
fi
echo -e "${GREEN}[OK] All keys verified (${TOTAL} .pk8 + ${TOTAL} .x509.pem)${NC}"
echo ""

# --- Create vendor directory for keys ---
echo -e "${CYAN}Setting up vendor/lineage-priv/keys/...${NC}"
mkdir -p vendor/lineage-priv
mv ~/.android-certs vendor/lineage-priv/keys

echo "PRODUCT_DEFAULT_DEV_CERTIFICATE := vendor/lineage-priv/keys/releasekey" > vendor/lineage-priv/keys/keys.mk

cat <<EOF > vendor/lineage-priv/keys/BUILD.bazel
filegroup(
    name = "android_certificate_directory",
    srcs = glob([
        "*.pk8",
        "*.pem",
    ]),
    visibility = ["//visibility:public"],
)
EOF

echo -e "${GREEN}[OK] Keys installed to vendor/lineage-priv/keys/${NC}"

# --- Backup keys ---
BACKUP_DIR=~/keys-backup/$(date +%Y%m%d_%H%M%S)
echo -e "${CYAN}Backing up keys to ${BACKUP_DIR}...${NC}"
mkdir -p "$BACKUP_DIR"
cp -r vendor/lineage-priv/keys/* "$BACKUP_DIR/"
echo -e "${GREEN}[OK] Backup saved to ${BACKUP_DIR}${NC}"

# --- Summary ---
echo ""
echo -e "${CYAN}============================================================${NC}"
echo -e "${GREEN}  ✅ SIGNING KEYS GENERATED SUCCESSFULLY${NC}"
echo -e "${CYAN}============================================================${NC}"
echo ""
echo -e "  Keys location : ${GREEN}vendor/lineage-priv/keys/${NC}"
echo -e "  Backup        : ${GREEN}${BACKUP_DIR}${NC}"
echo -e "  Keys count    : ${GREEN}${TOTAL} pairs (.pk8 + .x509.pem)${NC}"
echo ""
echo -e "  ${YELLOW}Next steps:${NC}"
echo -e "  1. Add to your device .mk file:"
echo -e "     ${CYAN}-include vendor/lineage-priv/keys/keys.mk${NC}"
echo -e "  2. Build as usual (keys will be used automatically)"
echo -e "  3. ${RED}KEEP YOUR BACKUP SAFE! Lost keys = no more OTA updates${NC}"
echo ""
