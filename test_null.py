import struct
import zlib
import os

# -----------------------------------------------------------
# КОНСТАНТЫ (из mp_ts_ids.h)
# -----------------------------------------------------------
PAT_PID = 0x0000
SDT_PID = 0x0011
NIT_PID = 0x0010
EIT_PID = 0x0012
TDT_PID = 0x0014
NULL_PID = 0x1FFF

# PID для нашего потока (как в рабочем примере)
P1_MAP_PID = 0x1000    # PMT PID
P1_VID_PID = 0x0100    # Video PID (256)
P1_AUD_PID = 0x0101    # Audio PID (257)
P1_PCR_PID = P1_VID_PID  # PCR берем из видео

# Константы для служебных таблиц
DEFAULT_NETWORK_ID = 1
DEFAULT_STREAM_ID = P1_MAP_PID
DEFAULT_SERVICE_ID = P1_MAP_PID
DEFAULT_PROGRAM_NR = P1_MAP_PID

# Типы потоков (ISO/IEC 13818-1)
STREAM_TYPE_H265 = 0x24  # H.265/HEVC
STREAM_TYPE_AAC = 0x0F   # AAC audio
STREAM_TYPE_MPEG2_VIDEO = 0x02  # MPEG-2 Video
STREAM_TYPE_MPEG1_AUDIO = 0x03  # MPEG-1 Audio
STREAM_TYPE_MPEG2_AUDIO = 0x04  # MPEG-2 Audio

# Дескрипторы SI (из dvb_si.h)
SI_DESC_SERVICE = 0x48
SVC_DIGITAL_TV = 0x01

# -----------------------------------------------------------
# ФУНКЦИЯ 1: CRC32 (из dvb_gen.c)
# -----------------------------------------------------------
def dvb_crc32_calc(data):
    """Вычисляет CRC32 как в DVB оборудовании"""
    crc = 0xFFFFFFFF
    for byte in data:
        for bit in range(7, -1, -1):
            bit_val = 1 if (crc & 0x80000000) else 0
            bit_val ^= 1 if (byte & (1 << bit)) else 0
            crc <<= 1
            if bit_val:
                crc ^= 0x04C11DB7
    return crc & 0xFFFFFFFF

def crc32_add(data):
    """Добавляет CRC32 в конец данных"""
    crc = dvb_crc32_calc(data)
    data.append((crc >> 24) & 0xFF)
    data.append((crc >> 16) & 0xFF)
    data.append((crc >> 8) & 0xFF)
    data.append(crc & 0xFF)
    return len(data)

# -----------------------------------------------------------
# ФУНКЦИЯ 2: Форматирование TS заголовка (из mp_tp.h)
# -----------------------------------------------------------
def tp_fmt(pid, payload_start=False, continuity_counter=0, adaptation_field_control=1):
    """Формирует заголовок TS пакета"""
    packet = bytearray(188)
    
    # Sync byte
    packet[0] = 0x47
    
    # Байт 1: transport_error_indicator(1) + payload_start(1) + transport_priority(1) + PID(5)
    packet[1] = 0
    if payload_start:
        packet[1] |= 0x40  # payload_unit_start_indicator
    
    # PID (13 бит)
    packet[1] |= (pid >> 8) & 0x1F
    packet[2] = pid & 0xFF
    
    # Байт 3: transport_scrambling_control(2) + adaptation_field_control(2) + continuity_counter(4)
    packet[3] = (adaptation_field_control << 4) | (continuity_counter & 0x0F)
    
    return packet

# -----------------------------------------------------------
# ФУНКЦИЯ 3: Добавление PCR поля (из pcr.c)
# -----------------------------------------------------------
def add_pcr_field(packet, offset, pcr_clk):
    """
    Добавляет PCR поле в адаптационное поле
    """
    # PCR = base * 300 + extension
    pcr_base = pcr_clk // 300
    pcr_ext = pcr_clk % 300
    
    # Упаковка PCR как в исходном коде
    packet[offset] = (pcr_base >> 25) & 0xFF
    packet[offset + 1] = (pcr_base >> 17) & 0xFF
    packet[offset + 2] = (pcr_base >> 9) & 0xFF
    packet[offset + 3] = (pcr_base >> 1) & 0xFF
    
    if pcr_base & 1:
        packet[offset + 4] = 0x80 | 0x7E
    else:
        packet[offset + 4] = 0x00 | 0x7E
    
    if pcr_ext & 0x100:
        packet[offset + 4] |= 1
    
    packet[offset + 5] = pcr_ext & 0xFF
    
    return 6

# -----------------------------------------------------------
# ФУНКЦИЯ 4: Создание PAT таблицы (из pat.c)
# -----------------------------------------------------------
def pat_fmt(transport_stream_id=1, program_number=1, pmt_pid=P1_MAP_PID):
    """Форматирует PAT таблицу"""
    pat = bytearray()
    
    pat.append(0x00)  # table_id
    pat.append(0xB0)  # section_syntax_indicator
    pat.append(0x00)  # section_length placeholder
    
    pat.append((transport_stream_id >> 8) & 0xFF)
    pat.append(transport_stream_id & 0xFF)
    
    pat.append(0xC2)  # version=2, current_next=1
    pat.append(0x00)  # section_number
    pat.append(0x00)  # last_section_number
    
    # Program 0 (NIT)
    pat.append(0x00)
    pat.append(0x00)
    pat.append(0xE0 | (NIT_PID >> 8))
    pat.append(NIT_PID & 0xFF)
    
    # Program 1
    pat.append((program_number >> 8) & 0xFF)
    pat.append(program_number & 0xFF)
    pat.append(0xE0 | (pmt_pid >> 8))
    pat.append(pmt_pid & 0xFF)
    
    section_length = len(pat) - 3 + 4
    pat[1] = (pat[1] & 0xF0) | ((section_length >> 8) & 0x0F)
    pat[2] = section_length & 0xFF
    
    crc32_add(pat)
    return bytes(pat)

# -----------------------------------------------------------
# ФУНКЦИЯ 5: Создание PMT таблицы (ИСПРАВЛЕНО)
# -----------------------------------------------------------
def pmt_fmt(program_number=1, pcr_pid=P1_VID_PID, 
            video_pid=P1_VID_PID, audio_pid=P1_AUD_PID):
    """Форматирует PMT таблицу с правильными stream_type"""
    pmt = bytearray()
    
    pmt.append(0x02)  # table_id
    pmt.append(0xB0)  # section_syntax_indicator
    pmt.append(0x00)  # section_length placeholder
    
    pmt.append((program_number >> 8) & 0xFF)
    pmt.append(program_number & 0xFF)
    
    pmt.append(0xC2)  # version=2, current_next=1
    pmt.append(0x00)  # section_number
    pmt.append(0x00)  # last_section_number
    
    # PCR PID
    pmt.append(0xE0 | (pcr_pid >> 8))
    pmt.append(pcr_pid & 0xFF)
    
    # program_info_length = 0
    pmt.append(0xF0)
    pmt.append(0x00)
    
    # ВИДЕО ПОТОК - используем H.265 (0x24)
    pmt.append(STREAM_TYPE_H265)  # stream_type H.265
    pmt.append(0xE0 | (video_pid >> 8))
    pmt.append(video_pid & 0xFF)
    pmt.append(0xF0)  # ES_info_length = 0
    pmt.append(0x00)
    
    # АУДИО ПОТОК - используем AAC (0x0F)
    pmt.append(STREAM_TYPE_AAC)  # stream_type AAC
    pmt.append(0xE0 | (audio_pid >> 8))
    pmt.append(audio_pid & 0xFF)
    pmt.append(0xF0)  # ES_info_length = 0
    pmt.append(0x00)
    
    section_length = len(pmt) - 3 + 4
    pmt[1] = (pmt[1] & 0xF0) | ((section_length >> 8) & 0x0F)
    pmt[2] = section_length & 0xFF
    
    crc32_add(pmt)
    return bytes(pmt)

# -----------------------------------------------------------
# ФУНКЦИЯ 6: Создание SDT таблицы (из sdt.c)
# -----------------------------------------------------------
def sdt_fmt(service_name="Radio", service_provider="R6WAX DATV",
            transport_stream_id=1, original_network_id=1, service_id=1):
    """Форматирует SDT таблицу"""
    sdt = bytearray()
    
    sdt.append(0x42)  # table_id
    sdt.append(0xF0)  # section_syntax_indicator
    sdt.append(0x00)  # section_length placeholder
    
    sdt.append((transport_stream_id >> 8) & 0xFF)
    sdt.append(transport_stream_id & 0xFF)
    
    sdt.append(0xC2)  # version=2, current_next=1
    sdt.append(0x00)  # section_number
    sdt.append(0x00)  # last_section_number
    
    sdt.append((original_network_id >> 8) & 0xFF)
    sdt.append(original_network_id & 0xFF)
    sdt.append(0xFF)  # reserved_future_use
    
    # service_id
    sdt.append((service_id >> 8) & 0xFF)
    sdt.append(service_id & 0xFF)
    
    # EIT flags, running status (0xFC = running)
    sdt.append(0xFC)
    
    # descriptors_loop_length (заполним позже)
    desc_len_pos = len(sdt)
    sdt.append(0x00)
    sdt.append(0x00)
    
    # Service descriptor
    sdt.append(SI_DESC_SERVICE)
    
    provider_bytes = service_provider.encode('utf-8')
    name_bytes = service_name.encode('utf-8')
    
    desc_len = 2 + len(provider_bytes) + 1 + len(name_bytes)
    sdt.append(desc_len)
    
    sdt.append(SVC_DIGITAL_TV)  # service_type
    
    sdt.append(len(provider_bytes))
    sdt.extend(provider_bytes)
    
    sdt.append(len(name_bytes))
    sdt.extend(name_bytes)
    
    # Обновляем descriptors_loop_length
    descriptors_loop_length = len(sdt) - (desc_len_pos + 2)
    sdt[desc_len_pos] = (descriptors_loop_length >> 8) & 0xFF
    sdt[desc_len_pos + 1] = descriptors_loop_length & 0xFF
    
    section_length = len(sdt) - 3 + 4
    sdt[1] = (sdt[1] & 0xF0) | ((section_length >> 8) & 0x0F)
    sdt[2] = section_length & 0xFF
    
    crc32_add(sdt)
    return bytes(sdt)

# -----------------------------------------------------------
# ФУНКЦИЯ 7: Создание правильного PES пакета для видео
# -----------------------------------------------------------
def create_video_pes_packet(pcr_base):
    """
    Создает правильный PES пакет для видео с PTS
    """
    pes = bytearray()
    
    # PES start code
    pes.extend([0x00, 0x00, 0x01, 0xE0])  # stream_id E0 = video
    
    # PES packet length (0 = undefined)
    pes.extend([0x00, 0x00])
    
    # PES header flags
    # Байт 6 (флаги): 0x80 = PTS_flag=1, 0x40 = DTS_flag=0, etc.
    pes.append(0x80)  # PTS_flag=1
    pes.append(0x00)  # остальные флаги = 0
    
    # PES header data length (5 байт для PTS)
    pes.append(0x05)
    
    # PTS в формате MPEG (33 бита)
    pts = pcr_base
    
    # Упаковка PTS как в спецификации
    pts1 = 0x21 | (((pts >> 30) & 0x07) << 1)
    pts2 = (pts >> 22) & 0xFF
    pts3 = 0x01 | (((pts >> 15) & 0x7F) << 1)
    pts4 = (pts >> 7) & 0xFF
    pts5 = 0x01 | ((pts & 0x7F) << 1)
    
    pes.append(pts1)
    pes.append(pts2)
    pes.append(pts3)
    pes.append(pts4)
    pes.append(pts5)
    
    # Добавляем H.265 start code и немного данных
    pes.extend([0x00, 0x00, 0x00, 0x01, 0x02, 0x01, 0xC0])  # H.265 NAL unit
    
    return bytes(pes)

# -----------------------------------------------------------
# ФУНКЦИЯ 8: Создание правильного PES пакета для аудио
# -----------------------------------------------------------
def create_audio_pes_packet():
    """
    Создает правильный PES пакет для аудио AAC
    """
    pes = bytearray()
    
    # PES start code для аудио
    pes.extend([0x00, 0x00, 0x01, 0xC0])  # stream_id C0 = audio
    
    # PES packet length (0 = undefined)
    pes.extend([0x00, 0x00])
    
    # PES header flags - без PTS для простоты
    pes.append(0x80)  # PTS_flag=0
    pes.append(0x00)
    pes.append(0x00)  # header length = 0
    
    # AAC ADTS header (очень простой)
    # Sync word (12 bits), ID (1 bit), layer (2 bits), etc.
    pes.extend([0xFF, 0xF1, 0x50, 0x80, 0x00, 0x1F, 0xFC])
    pes.extend([0x00] * 10)  # аудио данные
    
    return bytes(pes)

# -----------------------------------------------------------
# ФУНКЦИЯ 9: Создание TS пакета с секцией
# -----------------------------------------------------------
def create_section_packet(pid, section_data, continuity_counter):
    """
    Создает TS пакет с секцией (PAT, PMT, SDT)
    """
    packet = tp_fmt(pid, payload_start=True, 
                    continuity_counter=continuity_counter,
                    adaptation_field_control=1)
    
    # pointer_field = 0
    packet[4] = 0x00
    
    # Добавляем данные секции
    data_len = min(len(section_data), 183)
    packet[5:5+data_len] = section_data[:data_len]
    
    # Заполняем оставшееся место 0xFF
    for i in range(5+data_len, 188):
        packet[i] = 0xFF
    
    return bytes(packet)

# -----------------------------------------------------------
# ФУНКЦИЯ 10: Создание видео пакета с PCR
# -----------------------------------------------------------
def create_video_packet(pcr_base, continuity_counter):
    """
    Создает видео пакет с PCR полем
    """
    packet = tp_fmt(P1_VID_PID, payload_start=True,
                    continuity_counter=continuity_counter,
                    adaptation_field_control=3)  # adaptation + payload
    
    # Длина адаптационного поля
    packet[4] = 0x07
    
    # Флаги адаптационного поля (PCR_flag = 1)
    packet[5] = 0x10
    
    # Добавляем PCR поле
    add_pcr_field(packet, 6, pcr_base)
    
    # Создаем PES пакет
    pes_data = create_video_pes_packet(pcr_base)
    
    # Добавляем PES данные
    pes_len = min(len(pes_data), 176)  # 188 - 4 - 8 = 176
    packet[12:12+pes_len] = pes_data[:pes_len]
    
    # Заполняем оставшееся место
    for i in range(12+pes_len, 188):
        packet[i] = 0xFF
    
    return bytes(packet)

# -----------------------------------------------------------
# ФУНКЦИЯ 11: Создание аудио пакета
# -----------------------------------------------------------
def create_audio_packet(continuity_counter):
    """
    Создает аудио пакет
    """
    packet = tp_fmt(P1_AUD_PID, payload_start=True,
                    continuity_counter=continuity_counter,
                    adaptation_field_control=1)
    
    # Создаем PES пакет
    pes_data = create_audio_pes_packet()
    
    # Добавляем PES данные
    pes_len = min(len(pes_data), 184)
    packet[4:4+pes_len] = pes_data[:pes_len]
    
    # Заполняем оставшееся место
    for i in range(4+pes_len, 188):
        packet[i] = 0xFF
    
    return bytes(packet)

# -----------------------------------------------------------
# ФУНКЦИЯ 12: Создание NULL пакета
# -----------------------------------------------------------
def create_null_packet(continuity_counter):
    """
    Создает NULL пакет (PID 0x1FFF)
    """
    packet = tp_fmt(NULL_PID, payload_start=False,
                    continuity_counter=continuity_counter,
                    adaptation_field_control=1)
    
    for i in range(4, 188):
        packet[i] = 0xFF
    
    return bytes(packet)

# -----------------------------------------------------------
# ФУНКЦИЯ 13: Основная функция с правильным continuity counter
# -----------------------------------------------------------
def generate_stream(output_file="radio_stream.ts", num_groups=100):
    """
    Генерирует полный MPEG-TS поток с правильным continuity counter
    """
    print("=" * 70)
    print("ГЕНЕРАТОР MPEG-TS ПОТОКА (ФИНАЛЬНАЯ ВЕРСИЯ)")
    print("=" * 70)
    
    service_name = "Radio"
    service_provider = "R6WAX DATV"
    
    print(f"\nПараметры потока:")
    print(f"  Service Name: {service_name}")
    print(f"  Service Provider: {service_provider}")
    print(f"  Video PID: 0x{P1_VID_PID:04X} (H.265)")
    print(f"  Audio PID: 0x{P1_AUD_PID:04X} (AAC)")
    print(f"  PMT PID: 0x{P1_MAP_PID:04X}")
    print(f"  SDT PID: 0x{SDT_PID:04X}")
    
    # Создаем служебные таблицы
    pat_section = pat_fmt(transport_stream_id=1, program_number=1, pmt_pid=P1_MAP_PID)
    pmt_section = pmt_fmt(program_number=1, pcr_pid=P1_VID_PID,
                          video_pid=P1_VID_PID, audio_pid=P1_AUD_PID)
    sdt_section = sdt_fmt(service_name, service_provider,
                          transport_stream_id=1, original_network_id=1, service_id=1)
    
    print(f"\nРазмеры секций:")
    print(f"  PAT: {len(pat_section)} байт")
    print(f"  PMT: {len(pmt_section)} байт")
    print(f"  SDT: {len(sdt_section)} байт")
    
    # Генерируем поток
    packets_written = 0
    
    with open(output_file, "wb") as f:
        for group in range(num_groups):
            # Начальный счетчик непрерывности для группы
            # Важно: каждая группа начинается с 0, чтобы избежать ошибок
            cc = 0
            
            # PAT пакет
            pat_packet = create_section_packet(PAT_PID, pat_section, cc)
            f.write(pat_packet)
            cc = 1  # следующий пакет будет иметь счетчик 1
            packets_written += 1
            
            # PMT пакет
            pmt_packet = create_section_packet(P1_MAP_PID, pmt_section, cc)
            f.write(pmt_packet)
            cc = 2
            packets_written += 1
            
            # SDT пакет
            sdt_packet = create_section_packet(SDT_PID, sdt_section, cc)
            f.write(sdt_packet)
            cc = 3
            packets_written += 1
            
            # Видео пакет с PCR
            pcr_base = 900000 + group * 3000
            video_packet = create_video_packet(pcr_base, cc)
            f.write(video_packet)
            cc = 4
            packets_written += 1
            
            # Аудио пакет
            audio_packet = create_audio_packet(cc)
            f.write(audio_packet)
            cc = 5
            packets_written += 1
            
            # NULL пакет 1
            null1 = create_null_packet(cc)
            f.write(null1)
            cc = 6
            packets_written += 1
            
            # NULL пакет 2
            null2 = create_null_packet(cc)
            f.write(null2)
            packets_written += 1
            
            if group % 10 == 0:
                print(f"Сгенерировано групп: {group + 1}, пакетов: {packets_written}")
    
    file_size = os.path.getsize(output_file)
    print(f"\n" + "=" * 70)
    print(f"ГОТОВО! Файл '{output_file}' создан.")
    print(f"  Всего пакетов: {packets_written}")
    print(f"  Размер файла: {file_size} байт")
    print("=" * 70)
    
    # Проверяем первые пакеты
    print(f"\nПРОВЕРКА ПЕРВЫХ ПАКЕТОВ:")
    with open(output_file, "rb") as f:
        for i in range(7):
            packet = f.read(188)
            pid = ((packet[1] & 0x1F) << 8) | packet[2]
            cc = packet[3] & 0x0F
            pusi = (packet[1] & 0x40) >> 6
            
            type_str = "Unknown"
            if pid == PAT_PID:
                type_str = "PAT"
            elif pid == SDT_PID:
                type_str = "SDT"
            elif pid == P1_MAP_PID:
                type_str = "PMT"
            elif pid == P1_VID_PID:
                type_str = "VIDEO"
            elif pid == P1_AUD_PID:
                type_str = "AUDIO"
            elif pid == NULL_PID:
                type_str = "NULL"
            
            print(f"Пакет {i}: PID=0x{pid:04X} ({type_str}), PUSI={pusi}, CC={cc}")

if __name__ == "__main__":
    generate_stream("radio_stream.ts", 100)