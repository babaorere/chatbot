-- ============================================================================
-- Migration 005: Seed default knowledge base entries
-- ============================================================================
-- Default FAQs for the seed tenant (el_buen_trago).
-- Categories: horarios, productos, delivery, pagos, politicas
-- ============================================================================

-- Get the default tenant ID
DO $$
DECLARE
    v_tenant_id UUID;
BEGIN
    SELECT id INTO v_tenant_id FROM tenants WHERE slug = 'el_buen_trago' LIMIT 1;

    IF v_tenant_id IS NULL THEN
        RAISE NOTICE 'Default tenant not found. Skipping KB seed.';
        RETURN;
    END IF;

    -- HORARIOS
    INSERT INTO knowledge_base (tenant_id, category, title, content)
    VALUES
        (v_tenant_id, 'horarios', 'Horario de atención',
         'Lunes a Sábado: 10:00 - 22:00. Domingo: 12:00 - 20:00. Feriados: 12:00 - 20:00.'),
        (v_tenant_id, 'horarios', 'Horario de delivery',
         'El servicio de delivery está disponible de Lunes a Sábado de 11:00 a 21:30. Domingo de 13:00 a 19:30.'),
        (v_tenant_id, 'horarios', 'Días festivos',
         'En días festivos (18 de septiembre, 25 de diciembre, 1 de enero) el horario es reducido: 12:00 a 18:00.'),

    -- PRODUCTOS
        (v_tenant_id, 'productos', 'Variedad de cervezas',
         'Contamos con más de 50 variedades de cervezas nacionales e importadas, incluyendo artesanales.'),
        (v_tenant_id, 'productos', 'Vinos y espumantes',
         'Amplia selección de vinos chilenos (Casablanca, Maipo, Colchagua) y argentinos (Mendoza). También espumantes y champagnes.'),
        (v_tenant_id, 'productos', 'Licores premium',
         'Disponemos de licores premium: Johnnie Walker, Jack Daniels, Absolut, Grey Goose, Hendricks, y más.'),
        (v_tenant_id, 'productos', 'Pisco nacional',
         'Stock permanente de Pisco Control, Capel, Mistral, Portal y Viejo Calden en todas sus graduaciones.'),
        (v_tenant_id, 'productos', 'Consultar disponibilidad',
         'Si no encuentras un producto específico, consúltanos por WhatsApp o Telegram y te confirmamos disponibilidad en minutos.'),

    -- DELIVERY
        (v_tenant_id, 'delivery', 'Zonas de delivery',
         'Realizamos delivery dentro de Santiago. Costo: $2.000. Tiempo estimado: 30-60 minutos según zona.'),
        (v_tenant_id, 'delivery', 'Monto mínimo de pedido',
         'El monto mínimo para pedidos a domicilio es de $10.000. No hay mínimo para retiro en tienda.'),
        (v_tenant_id, 'delivery', 'Formas de pago delivery',
         'Aceptamos transferencia bancaria, efectivo contra entrega y tarjetas de débito/crédito en delivery.'),
        (v_tenant_id, 'delivery', 'Seguimiento de pedido',
         'Una vez confirmado tu pedido, recibirás un mensaje con el estado y tiempo estimado de entrega.'),

    -- PAGOS
        (v_tenant_id, 'pagos', 'Medios de pago aceptados',
         'Aceptamos efectivo, tarjetas de débito y crédito (Visa, Mastercard, Redcompra), y transferencia bancaria.'),
        (v_tenant_id, 'pagos', 'Facturación electrónica',
         'Emitimos boleta y factura electrónica. Solicítala al momento de tu compra indicando tus datos.'),
        (v_tenant_id, 'pagos', 'Descuentos por volumen',
         'Para compras al por mayor (más de 10 unidades del mismo producto), consulta por descuentos especiales.'),

    -- POLITICAS
        (v_tenant_id, 'politicas', 'Política de devoluciones',
         'No se aceptan devoluciones de productos abiertos. Productos cerrados con defecto pueden ser cambiados dentro de 48 horas.'),
        (v_tenant_id, 'politicas', 'Venta a mayores de 18',
         'Por ley, solo vendemos alcohol a mayores de 18 años. Se puede solicitar identificación en delivery.'),
        (v_tenant_id, 'politicas', 'Promociones vigentes',
         'Revisa nuestras promociones semanales en nuestro canal de Telegram o preguntando aquí mismo.'),
        (v_tenant_id, 'politicas', 'Contacto humano',
         'Si necesitas atención personalizada, escribe "humano" y te conectaremos con un agente real.'),

    -- SERVICIOS
        (v_tenant_id, 'servicios', 'Eventos y catering',
         'Ofrecemos servicio de bar para eventos. Cotización personalizada según cantidad de invitados y duración.'),
        (v_tenant_id, 'servicios', 'Gift cards',
         'Vendemos gift cards de $10.000, $20.000 y $50.000. Ideales para regalos. Válidas por 6 meses.')

    ON CONFLICT DO NOTHING;

    RAISE NOTICE 'Seeded % KB entries for tenant el_buen_trago.', (SELECT COUNT(*) FROM knowledge_base WHERE tenant_id = v_tenant_id);
END $$;
